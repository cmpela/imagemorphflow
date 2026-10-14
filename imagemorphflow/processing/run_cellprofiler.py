# imagemorphflow/processing/run_analysis.py

import os
import sys
import subprocess
import argparse
from imagemorphflow.utils import run_cellprofiler_utils
from pathlib import Path
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description="Activate env and run analysis")
    parser.add_argument("--config", type=str, required=True, help="Path to config.yaml")
    args = parser.parse_args()

    username = os.environ.get("USER") or os.environ.get("USERNAME")
    if not username:
        print("USER or USERNAME environment variable not set.")
        sys.exit(1)

    # Prepare log file path
    project_name = extract_project_name(args.config)
    base_path = Path.home() / "projects" / project_name / "workspace"
    log_dir = base_path / "logs" / "run_cellprofiler"
    os.makedirs(log_dir, exist_ok=True)

    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"{current_time}_run.log")

    # Command to activate conda and run the real processing script
    command = [
        "python",
        "-m",
        "imagemorphflow.utils.run_cellprofiler_utils",
        "--config",
        args.config,
    ]

    # Execute and redirect output
    with open(log_path, "w") as log_file:
        process = subprocess.Popen(
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        process.communicate()

    if process.returncode != 0:
        print(f"[ERROR] run_analysis failed. See log: {log_path}")
    else:
        print(f"[OK] run_analysis completed. Log saved at: {log_path}")


def extract_project_name(config_path):
    import yaml

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config.get("project_name", "unknown_project")


if __name__ == "__main__":
    main()
