import os
import pandas as pd
import zlib
import sqlite3

from pathlib import Path

def checksum(pathname, buffer_size=65536):
    """
    Generate a 32-bit unique identifier for a file.
    """
    with open(pathname, "rb") as stream:
        result = zlib.crc32(bytes(0))
        while True:
            buffer = stream.read(buffer_size)
            if not buffer:
                break
            result = zlib.crc32(buffer, result)
    return result & 0xFFFFFFFF


def get_identifier_columns(df):
    return [
        col for col in df.columns
        if (
            col == "TableNumber"
            or col == "ImageNumber"
            or col == "ObjectNumber"
            or col.startswith("Metadata_")
            or "_Metadata_" in col
            or "_Parent_" in col
        )
    ]


def column_contains_channel(col, channel):
    return col.endswith(f"_{channel}") or f"_{channel}_" in col


def split_table_by_extra_channels(df, table_name, extra_channels):
    id_cols = get_identifier_columns(df)

    main_cols = [
        col for col in df.columns
        if col in id_cols
        or not any(column_contains_channel(col, channel) for channel in extra_channels)
    ]

    split_tables = {
        table_name: df.loc[:, list(dict.fromkeys(main_cols))]
    }

    for channel in extra_channels:
        extra_cols = [
            col for col in df.columns
            if col in id_cols or column_contains_channel(col, channel)
        ]

        split_tables[f"{table_name}_{channel}_extra"] = df.loc[
            :, list(dict.fromkeys(extra_cols))
        ]

    return split_tables


def get_split_extra_channels_config(config):
    """
    Read optional split-extra-channel settings from the ingest config.
    """
    split_config = config.get("ingest", {}).get("split_extra_channels", [])

    if isinstance(split_config, dict):
        if not split_config.get("enabled", True):
            return [], []
        channels = split_config.get("channels", [])
        compartments = split_config.get("compartments", ["Cells", "Cytoplasm", "Nuclei"])
        return channels, compartments

    if isinstance(split_config, list):
        return split_config, ["Cells", "Cytoplasm", "Nuclei"]

    return [], []


def ingest_to_db(source, config, output_db_path, skip_image_prefix=True):
    """
    Reads all subdirectories in `source`, validates and ingests CSVs as SQLite DB tables.
    Mimics cytominer_database.ingest.seed but with SQLite output.
    """
    directories = sorted(
        [
            os.path.join(source, directory)
            for directory in os.listdir(source)
            if os.path.isdir(os.path.join(source, directory))
        ]
    )
    print("Project name inside ingest_to_db:", config.get("project_name"))

    extra_channels, split_compartments = get_split_extra_channels_config(config)
    split_compartments = set(split_compartments)

    if extra_channels:
        print("Splitting extra channels into auxiliary tables:", extra_channels)

    tables_data = {}
    for directory in directories:
        try:
            image_csv = os.path.join(directory, config["filenames"]["image"])
            compartment_files = []

            for filename in config["filenames"].values():
                if filename != config["filenames"]["image"]:
                    file_path = os.path.join(directory, filename)
                    if os.path.exists(file_path):
                        compartment_files.append(file_path)

            for file_path in [image_csv] + compartment_files:
                if not os.path.isfile(file_path) or os.stat(file_path).st_size == 0:
                    raise IOError(f"File missing or empty: {file_path}")
        except Exception as error:
            print(f"Skipping {directory}: {error}")
            continue

        identifier = checksum(image_csv)

        name, _ = os.path.splitext(config["filenames"]["image"])
        df_img = pd.read_csv(image_csv, sep=None, engine="python")

        project_name = config.get("project_name", "")

        essential_image_cols = [
            "ImageNumber",
            "ObjectNumber",
            "Metadata_Plate",
            "Metadata_Well",
            "Metadata_Site",
            "Count_Cells",
            "Count_Nuclei",
            "Count_Cytoplasm",
            "Count_Binuclei",
            "Math_Measurement",
        ]

        if project_name == "20260429_CL2025" or project_name == "rpe1":
            keep_cols = [
                col for col in df_img.columns
                if (
                    col.startswith("ImageQuality_")
                    or col in essential_image_cols
                )
            ]

            df_img = df_img[keep_cols]

        if not skip_image_prefix:
            no_prefix = ["ImageNumber", "ObjectNumber"]
            df_img.columns = [
                col if col in no_prefix else f"{name.capitalize()}_{col}"
                for col in df_img.columns
            ]

        df_img.insert(0, "TableNumber", identifier)
        tables_data.setdefault(name.capitalize(), []).append(df_img)

        for comp_csv in compartment_files:
            # table_name, _ = os.path.splitext(os.path.basename(comp_csv))
            # table_name = table_name.capitalize()
            table_name = Path(comp_csv).stem
            print(table_name)

            df = pd.read_csv(comp_csv, sep=None, engine="python")
            if table_name == "InnerCells":
                innercells_cols = [
                    "ImageNumber",
                    "ObjectNumber",
                    "Math_GFPDelta",
                ]

                missing_cols = [
                    col for col in innercells_cols
                    if col not in df.columns
                ]

                if missing_cols:
                    raise ValueError(
                        f"Missing required InnerCells columns: {missing_cols}"
                    )

                df = df[innercells_cols]
            no_prefix = ["ImageNumber", "ObjectNumber"]
            df.columns = [
                col if col in no_prefix else f"{table_name}_{col}"
                for col in df.columns
            ]
            df.insert(0, "TableNumber", identifier)

            if extra_channels and table_name in split_compartments:
                split_tables = split_table_by_extra_channels(
                    df=df,
                    table_name=table_name,
                    extra_channels=extra_channels,
                )
                for split_table_name, split_df in split_tables.items():
                    tables_data.setdefault(split_table_name, []).append(split_df)
            else:
                tables_data.setdefault(table_name, []).append(df)

    if tables_data:
        os.makedirs(os.path.dirname(output_db_path), exist_ok=True)
        conn = sqlite3.connect(output_db_path)
        for table_name, dfs in tables_data.items():
            merged_df = pd.concat(dfs, ignore_index=True)
            merged_df.to_sql(table_name, conn, if_exists="replace", index=False)
            print(
                f"Wrote table '{table_name}' with "
                f"{len(merged_df)} rows and {len(merged_df.columns)} columns"
            )
        conn.close()
        print(f"Database written to {output_db_path}")
    else:
        print("No data found to write.")
