#!/usr/bin/env python3

import argparse
import re
import warnings
from pathlib import Path
import pandas as pd


def read_table(filepath):
    """
    Read a CSV or TSV file based on file suffix.
    """
    filepath = Path(filepath)
    suffix = filepath.suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(filepath)
    if suffix == ".tsv":
        return pd.read_csv(filepath, sep="\t")

    raise ValueError(f"Unsupported file format for {filepath}. Use .csv or .tsv")


def find_required_columns(df):
    """
    Find required columns using prioritized exact matches first,
    then fallback pattern matching.
    """
    cols = list(df.columns)
    cols_lower = {c.lower(): c for c in cols}

    def find_one(preferred, contains=None, regex=None, name="column"):
        for p in preferred:
            if p.lower() in cols_lower:
                return cols_lower[p.lower()]

        if contains:
            candidates = [c for c in cols if any(x in c.lower() for x in contains)]
        elif regex:
            candidates = [c for c in cols if re.search(regex, c.lower())]
        else:
            candidates = []

        if len(candidates) == 0:
            raise ValueError(f"No {name} found. Available columns: {cols}")

        if len(candidates) > 1:
            print(f"Warning: multiple {name} candidates found: {candidates}. Using first.")

        return candidates[0]

    mapping = {
        "well": find_one(
            preferred=["Metadata_Well", "well_position"],
            contains=["well"],
            name="well column",
        ),
        "container": find_one(
            preferred=["Container_ID", "Container_Id"],
            regex=r"container.*id",
            name="container column",
        ),
        "conc": find_one(
            preferred=["Conc_uM", "Conc (uM)", "Conc_um"],
            regex=r"conc.*(um|µm)",
            name="concentration column",
        ),
        "producer": find_one(
            preferred=["Producer"],
            contains=["producer", "supplier", "vendor"],
            name="producer column",
        ),
    }

    return mapping


def normalize_well_format(series):
    """
    Normalize well names like A1 -> A01, A12 -> A12.
    """
    tmp = series.astype(str).str.extract(r"([A-Za-z])(\d+)")
    return tmp[0].str.upper() + tmp[1].astype(int).astype(str).str.zfill(2)


def process_layout(platemap_path, annot_path, negcon, plate_name):
    """
    Build final layout table from platemap and annotation files.
    """
    platemap = read_table(platemap_path)
    annot = read_table(annot_path)

    initial_layout = annot.merge(platemap, on="Trivial_Name", how="right")

    if not initial_layout.query(negcon).empty:
        cols = find_required_columns(initial_layout)
        well_col = cols["well"]

        initial_layout[["well_row", "well_col"]] = initial_layout[well_col].astype(str).str.extract(r"([A-Z])(\d+)")
        initial_layout["well_col"] = initial_layout["well_col"].astype(int)

        ctrl_cols = sorted(initial_layout.query(negcon)["well_col"].unique().tolist())

        if ctrl_cols == [11, 12]:
            print("Use ctrl_cols = [11, 12] for profile generation.")
        else:
            well_list = initial_layout.query(negcon)[well_col].tolist()
            print(f"Use ctrl_range = {well_list}")

        initial_layout = initial_layout.query(f"not ({negcon})").reset_index(drop=True)
    else:
        warnings.warn("No negative controls found with the provided query.")

    cols = find_required_columns(initial_layout)

    initial_layout = initial_layout.rename(
        columns={
            cols["well"]: "Address_384",
            cols["container"]: "Container_Id",
            cols["conc"]: "Conc_uM",
            cols["producer"]: "Producer",
        }
    )

    initial_layout["V"] = 1
    initial_layout["Plate_name_384"] = plate_name

    final_layout = initial_layout[
        ["V", "Container_Id", "Conc_uM", "Plate_name_384", "Address_384", "Producer"]
    ].copy()

    final_layout["Address_384"] = normalize_well_format(final_layout["Address_384"])

    return final_layout


def main():
    parser = argparse.ArgumentParser(
        description="Build a standardized 384-well layout table from platemap and annotation files."
    )
    parser.add_argument(
        "--platemap",
        required=True,
        help="Path to platemap file (.csv or .tsv).",
    )
    parser.add_argument(
        "--annot",
        required=True,
        help="Path to annotation file (.csv or .tsv).",
    )
    parser.add_argument(
        "--negcon",
        default="Trivial_Name == 'DMSO'",
        help="Pandas query string defining negative controls.",
    )
    parser.add_argument(
        "--plate-name",
        required=True,
        help="Value to assign to Plate_name_384.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path (.csv or .tsv).",
    )

    args = parser.parse_args()

    final_layout = process_layout(
        platemap_path=args.platemap,
        annot_path=args.annot,
        negcon=args.negcon,
        plate_name=args.plate_name,
    )

    output_path = Path(args.output)
    suffix = output_path.suffix.lower()

    if suffix == ".csv":
        final_layout.to_csv(output_path, index=False)
    elif suffix == ".tsv":
        final_layout.to_csv(output_path, sep="\t", index=False)
    else:
        raise ValueError("Output file must end with .csv or .tsv")

    print(f"Saved output to: {output_path}")


if __name__ == "__main__":
    main()