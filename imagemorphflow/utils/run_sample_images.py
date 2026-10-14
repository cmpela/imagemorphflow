#!/usr/bin/env python3

"""Run sample_images.sh for every plate defined in a project mapping."""

import argparse
import getpass
import json
import subprocess
from pathlib import Path

import yaml


def format_path(path_template, config):
    """Expand supported placeholders in a configured path."""

    return Path(
        path_template.format(
            username=getpass.getuser(),
            project_name=config["project_name"],
        )
    ).expanduser()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Read plate names from the configured symlinks JSON and call "
            "sample_images.sh once for each plate."
        )
    )
    parser.add_argument("config", type=Path, help="Path to the YAML config file.")
    parser.add_argument(
        "--sample-script",
        type=Path,
        default=Path(__file__).with_name("sample_images.sh"),
        help="Path to sample_images.sh. Default: next to this wrapper.",
    )
    parser.add_argument(
        "--destination-root",
        type=Path,
        default=None,
        help=(
            "Root output directory. Default: "
            "<project>/images/representative."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the commands without running image conversion.",
    )
    parser.add_argument(
        "--overlay",
        action="append",
        default=[],
        help=(
            "Channel combination to generate as a colored crop overlay. "
            "Can be provided multiple times, for example: "
            "--overlay w5+w3 --overlay w4+w2."
        ),
    )
    args = parser.parse_args()

    config_path = args.config.expanduser().resolve()
    sample_script = args.sample_script.expanduser().resolve()

    if not config_path.is_file():
        raise FileNotFoundError(f"Config file does not exist: {config_path}")

    if not sample_script.is_file():
        raise FileNotFoundError(
            f"sample_images.sh does not exist: {sample_script}"
        )

    with config_path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)

    image_root = format_path(config["image_path"], config)
    workspace = format_path(config["base_path"], config)
    mapping_path = workspace / "symlinks" / config["symlinks_file"]

    if not image_root.is_dir():
        raise FileNotFoundError(f"Image root does not exist: {image_root}")

    if not mapping_path.is_file():
        raise FileNotFoundError(f"Plate mapping does not exist: {mapping_path}")

    if args.destination_root is None:
        destination_root = workspace.parent / "images" / "representative"
    else:
        destination_root = args.destination_root.expanduser().resolve()

    with mapping_path.open("r", encoding="utf-8") as stream:
        plate_mapping = json.load(stream)

    if not isinstance(plate_mapping, dict) or not plate_mapping:
        raise ValueError(f"Plate mapping is empty or invalid: {mapping_path}")

    print(f"Image root: {image_root}", flush=True)
    print(f"Plate mapping: {mapping_path}", flush=True)
    print(f"Destination root: {destination_root}", flush=True)
    print(f"Sample script: {sample_script}", flush=True)

    failures = []

    for plate_old, plate_new in plate_mapping.items():
        source_dir = image_root / plate_old
        destination_dir = destination_root / plate_new

        print(f"\n{plate_old} -> {plate_new}", flush=True)
        print(f"Source: {source_dir}", flush=True)
        print(f"Destination: {destination_dir}", flush=True)

        if not source_dir.is_dir():
            print("Warning: source directory does not exist; skipping.", flush=True)
            failures.append(plate_old)
            continue

        command = [
            "bash",
            str(sample_script),
            str(source_dir),
            str(destination_dir),
            str(config["project_name"]),
            *args.overlay,
        ]

        if args.dry_run:
            print("Command: " + " ".join(command), flush=True)
            continue

        # sample_images.sh requires DEST_DIR itself to exist.
        destination_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            print(
                f"Warning: sample_images.sh failed with exit code "
                f"{result.returncode}.",
                flush=True,
            )
            failures.append(plate_old)

    if failures:
        raise SystemExit(
            "Processing failed or source images were missing for: "
            + ", ".join(failures)
        )


if __name__ == "__main__":
    main()
