# Written by Fernanda Garcia Fossa
import os
import yaml
import json
import pandas as pd
from pathlib import Path
from imagemorphflow.utils import file_utils, join_profiles_utils


def load_config(config_path):
    with open(config_path, "r") as f:
        if config_path.endswith(".yaml") or config_path.endswith(".yml"):
            return yaml.safe_load(f)
        elif config_path.endswith(".json"):
            return json.load(f)
        else:
            raise ValueError("Config must be YAML or JSON")


def load_symlink_mappings(json_path):
    with open(json_path, "r") as f:
        return json.load(f)


def process_all_plates(config_path):
    config = load_config(config_path)
    username = os.environ.get("USER") or os.environ.get("USERNAME") or "default_user"

    # Resolve output base path for backend
    base_path = config["base_path"].format(
        username=username, project_name=config["project_name"]
    )
    backend_path = os.path.join(base_path, "backend")
    # Path to symlinks json
    output_dir = Path(base_path)
    json_file = output_dir / "symlinks" / config["symlinks_file"]
    symlink_mappings = load_symlink_mappings(json_file)

    logger = file_utils.setup_logging(config, base_path, pipeline="join_profiles")
    logger.info("🚀 Starting plate processing loop")

    df_list = []
    dfs_aggregate = []
    dfs_aggregate_annotate = []
    for plate_old, plate_new in symlink_mappings.items():
        plate_dir = os.path.join(backend_path, plate_new)
        if not os.path.isdir(plate_dir):
            logger.warning(f"⚠️ Plate directory not found: {plate_dir}, skipping.")
            continue
        # db_path = os.path.join(plate_dir, f"{plate_new}.db")
        logger.info(f"\n\n🧪 Processing plate {plate_new}\n")
        extra_channels = config.get("ingest", {}).get("split_extra_channels", [])
        profile_dir, df = join_profiles_utils.join_and_aggregate(
            base_path,
            plate_new,
            config["project_name"],
            extra_channels=extra_channels,
        )
        dfs_aggregate.append(df)
        if config["annotate"]["perform"]:
            logger.info(f"Annotating {plate_new}")
            df_annot = join_profiles_utils.annotate(
                df, config["annotate"]["platemap"], profile_dir
            )
            dfs_aggregate_annotate.append(df_annot)
            if config["normalize"]["perform"]:
                logger.info(f"Normalizing {plate_new}")
                features, metadata = join_profiles_utils.get_features_and_metadata(
                    df_annot
                )
                df_norm, filename = join_profiles_utils.normalize(
                    df_annot,
                    features,
                    metadata,
                    profile_dir,
                    normalize_to_negcon=config["normalize"]["to_negcons"],
                )
                df_list.append(df_norm)

    # Export all dfs joined, but only with aggregation
    combined_profile_dir = os.path.join(base_path, "profiles", "all")
    os.makedirs(combined_profile_dir, exist_ok=True)
    filename_base = os.path.splitext(config["symlinks_file"])[0]

    df_g = pd.concat(dfs_aggregate, ignore_index=True)
    df_g.to_csv(
        os.path.join(combined_profile_dir, f"{filename_base}_allplates_agg.tsv"),
        sep="\t",
        index=False,
    )

    if config["annotate"]["perform"]:
        df_g_n = pd.concat(dfs_aggregate_annotate, ignore_index=True)
        df_g_n.to_csv(
            os.path.join(
                combined_profile_dir, f"{filename_base}_allplates_agg_annot.tsv"
            ),
            sep="\t",
            index=False,
        )

    if config["feature_selection"]["perform"]:
        logger.info(
            "\n\n🔬 Performing feature selection on all concatenated profiles\n"
        )
        df_all = pd.concat(df_list, ignore_index=True)

        features, metadata = join_profiles_utils.get_features_and_metadata(df_all)

        join_profiles_utils.feature_selection(
            df_all,
            features,
            combined_profile_dir,
            filename=filename_base,
            logger=logger,
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Open .db and process it using pycytominer's SingleCells."
    )
    parser.add_argument(
        "--config", required=True, help="Path to main project YAML config."
    )
    args = parser.parse_args()
    process_all_plates(args.config)
