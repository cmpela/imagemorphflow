# Written by Fernanda Garcia Fossa
# Inspired by cytominer_database.ingest, now deprecated
import os
from pathlib import Path
import yaml
import json
from imagemorphflow.utils import ingest_profiles_utils, file_utils


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

    logger = file_utils.setup_logging(config, base_path, pipeline="ingest_profiles")
    logger.info("🚀 Starting ingest profiles")

    # The config for ingest_to_db
    ingest_config = {
        "project_name": config["project_name"],
        "filenames": {
            "image": "Image.txt",
            "cells": "Cells.txt",
            "cytoplasm": "Cytoplasm.txt",
            "nuclei": "Nuclei.txt",
            # "innercells": "InnerCells.txt", # was used for the hek293 project for singlecell information retrieval
        },
        "ingest": config.get("ingest", {}),
    }

    for plate_old, plate_new in symlink_mappings.items():
        logger.info(f"🧪 Processing plate {plate_new}")
        plate_dir = os.path.join(backend_path, plate_new)
        if not os.path.isdir(plate_dir):
            print(f"Plate directory not found: {plate_dir}, skipping.")
            continue
        db_path = os.path.join(plate_dir, f"{plate_new}.db")
        print(f"\nProcessing plate {plate_new} → {db_path}")
        ingest_profiles_utils.ingest_to_db(
            source=plate_dir,
            config=ingest_config,
            output_db_path=db_path,
            skip_image_prefix=True,  # or False, your choice
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Process all plates and ingest to .db using project config."
    )
    parser.add_argument(
        "--config", required=True, help="Path to main project YAML config."
    )
    args = parser.parse_args()
    process_all_plates(args.config)
