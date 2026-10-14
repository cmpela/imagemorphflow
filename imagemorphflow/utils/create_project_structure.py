import os
import argparse
from pathlib import Path


def create_project_structure(base_dir: str):
    base = Path(base_dir)

    dirs_to_create = [
        "images/illum",
        "images/masks",
        "images/images",
        "workspace/analysis",
        "workspace/assaydev",
        "workspace/backend",
        "workspace/deeplearning",
        "workspace/deeplearning/cellpose",
        "workspace/deeplearning/sam",
        "workspace/loaddata",
        "workspace/logs",
        "workspace/notebooks",
        "workspace/pipelines",
        "workspace/plate_overview",
        "workspace/plate_overview/overlays",
        "workspace/plate_overview/branchpoints",
        "workspace/plate_overview/plates",
        "workspace/profiles",
        "workspace/scripts",
        "workspace/symlinks",
        "workspace/temp",
        "workspace/tests",
    ]

    for subdir in dirs_to_create:
        path = base / subdir
        path.mkdir(parents=True, exist_ok=True)

    print(f"Directory structure created at {base_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create project directory structure")
    parser.add_argument(
        "--base_dir", type=str, required=True, help="Base directory path"
    )
    args = parser.parse_args()

    create_project_structure(args.base_dir)
