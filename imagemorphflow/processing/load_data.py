import os
import glob
import argparse
import json
from pathlib import Path
from imagemorphflow.utils import file_utils, load_data_utils


def generate_load_data(config_path):
    """Main function to generate the load_data.csv file."""
    config = file_utils.load_config(config_path)
    username = os.environ.get("USER") or os.environ.get("USERNAME") or "default_user"
    project_name = config["project_name"]
    output_dir_template = config["base_path"]
    output_dir = Path(
        output_dir_template.format(username=username, project_name=project_name)
    )

    logger = file_utils.setup_logging(
        config, base_path=output_dir, pipeline="load_data"
    )

    selected_microscope = config["microscope"]
    microscope_config = config["microscopes"].get(selected_microscope)
    if not microscope_config:
        raise ValueError(
            f"Microscope '{selected_microscope}' is not defined in config.yaml"
        )

    home_dir = Path.home()

    json_file = output_dir / "symlinks" / config["symlinks_file"]
    image_dir = Path(config["image_path"])
    if config.get("use_scratch", False):
        image_dir = Path(config.get("scratch_image_path", "/mnt/scratch"))

    images_folder_symlink = home_dir / "projects" / project_name / "images" / "images"

    # file_utils.create_symlinks(image_dir, json_file, images_folder_symlink)
    output_dir = output_dir / "loaddata"

    regex_image = microscope_config["regex_image"]
    regex_plate = microscope_config["regex_plate"]
    input_folder_pattern = microscope_config["input_folder_pattern"]

    masks_config = config.get("masks", {})
    include_masks = masks_config.get("include_masks", False)
    mask_channels = masks_config.get("mask_channels", {})
    mask_output_dir = masks_config.get("mask_output_dir", None)
    segmentation_method = masks_config.get("segmentation_method", None)

    symlink_mappings = file_utils.load_symlink_mappings(json_file)

    for plate_old, plate_new in symlink_mappings.items():
        if plate_new:
            input_folder_path = input_folder_pattern.format(
                image_dir=image_dir, plate_old=plate_old
            )

            if "*" in str(input_folder_path):
                input_folders = glob.glob(input_folder_path)
                if not input_folders:
                    logger.warning(
                        f"Warning: No matching files found for {input_folder_path}"
                    )
                    continue
                input_folder_ordered = sorted(input_folders, key=os.path.getmtime)
                input_folder = Path(
                    input_folder_ordered[-1]
                )  # get the most recent folder only!!
                plate_base = images_folder_symlink / plate_new
                if plate_base.is_symlink():
                    plate_base.unlink()
                plate_base.mkdir(parents=True, exist_ok=True)
                plate_old_root = Path(image_dir) / plate_old
                suffix = input_folder.relative_to(plate_old_root)
                
                plate_link = plate_base / suffix
                plate_link.parent.mkdir(parents=True, exist_ok=True)

                latest_src = input_folder

                try:
                    latest_src.resolve().relative_to(plate_base.resolve())
                    raise RuntimeError(f"Refusing to create recursive symlink: source {latest_src} is inside {plate_base}")
                except ValueError:
                    pass

                if plate_link.exists() or plate_link.is_symlink():
                    if plate_link.is_symlink():
                        plate_link.unlink()
                    else:
                        raise RuntimeError(f"{plate_link} exists and is not a symlink; refusing to overwrite.")

                if not latest_src.exists():
                    raise FileNotFoundError(f"Symlink source does not exist: {latest_src}")

                os.symlink(str(latest_src), str(plate_link))
                images_folder_input = plate_link
            else:
                input_folder = Path(input_folder_path)
                images_folder_input = images_folder_symlink / plate_new
                file_utils.create_symlinks(image_dir, json_file, images_folder_symlink)

            illum_folder = (
                home_dir / "projects" / project_name / "images" / "illum" / plate_new
            )
            loaddata_folder_output = output_dir / plate_new

            load_data_utils.generate_load_data(
                logger,
                str(input_folder),
                config["channels"],
                regex_image=regex_image,
                regex_plate=regex_plate,
                output_dir_bool=True,
                output_dir=str(loaddata_folder_output),
                cluster=True,
                cluster_img_folder=str(images_folder_input),
                cluster_illum_folder=str(illum_folder),
                provide_plate_name=True,
                plate_name=plate_new,
                include_masks=include_masks,
                mask_output_dir=(
                    mask_output_dir.format(
                        username=username, project_name=project_name, plate_new=plate_new
                    )
                    if mask_output_dir
                    else None
                ),
                mask_channels=mask_channels,
                segmentation_method=segmentation_method,
            )

            logger.info(f"Load data files saved in: {loaddata_folder_output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate load_data.csv file")
    parser.add_argument("--config", type=str, required=True, help="Path to config.yaml")
    args = parser.parse_args()

    print(f"Running load_data.py with config: {args.config}")
    generate_load_data(args.config)
