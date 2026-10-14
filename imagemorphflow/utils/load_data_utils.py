import pandas as pd
import numpy as np
import re
import os
from PIL import Image
from os import walk


def get_image_width(image_path, logger):
    """
    It may be necessary to have the image width when wanting to crop cells.
    """
    try:
        with Image.open(image_path) as img:
            width, _ = img.size
            return width
    except Exception as e:
        logger.error(f"Failed to get image width for {image_path}: {e}", exc_info=True)
        return None


def remove_path_cols(df, prefix="PathName_"):
    # Specify the prefix you want to remove
    prefix_to_remove = prefix

    # Use the filter function to select columns with the specified prefix
    filtered_columns = df.filter(like=prefix_to_remove, axis=1)

    # Use the drop method to remove the selected columns
    df = df.drop(columns=filtered_columns)
    return df


def generate_load_data(
    logger,
    input_folder,
    ch_dic,
    regex_image=r"(?P<Well>[A-P][0-9]{1,2})_s(?P<Site>[0-9]{1,2})_(?P<Channel>w[0-9])(?!.*_thumbnail)",
    regex_plate=r".*[\\/](?P<Plate>.*)",
    output_dir_bool=False,
    output_dir=None,
    cluster=False,
    cluster_img_folder=None,
    cluster_illum_folder=None,
    provide_plate_name=False,
    plate_name=None,
    include_masks=False,
    mask_output_dir=None,
    mask_channels=None,
    segmentation_method=None,
):
    """
    Generates a CSV file containing info about image location, metadata well, site and plate, for each channel defined in the ch_dic provided.

    """

    logger.info(f"Images got from: {input_folder}")

    illum_list = [True, False]

    for illum_bool in illum_list:
        df = pd.DataFrame()
        if provide_plate_name:
            plate = plate_name
        else:
            regex_plate = regex_plate
            plate_search = re.search(regex_plate, input_folder)
            platefind = plate_search.group("Plate")
            plate = platefind.replace(" ", "_")
        if cluster:
            images_dir = cluster_img_folder
            illum_dir = cluster_illum_folder
        else:
            images_dir = input_folder
            illum_dir = input_folder + r"/illum"
        # filesname and channel
        files = []
        for dirpath, dirnames, filenames in walk(input_folder):
            for file in filenames:
                if "thumb" in file:
                    continue
                if re.search(regex_image, file):
                    files.append(file)
            files = sorted(files)
            break
        # find channels
        channels = []
        regex = regex_image
        for f in files:
            matches = re.search(regex, f)
            if matches:
                channels.append(matches.group("Channel"))
        # channels = np.array(channels)
        ch_unique = np.unique(channels)
        # check number of inputs channels == channels found
        number_of_channel_input = len(ch_dic)
        number_of_channel_regex = len(ch_unique)
        if number_of_channel_input != number_of_channel_regex:
            logger.warning(
                f"WARNING: The number of channels you gave ({number_of_channel_input}) are different from the ones we found ({number_of_channel_regex})."
            )
        # create columns with files and pathnames
        temp_list = []
        illum_list = []
        for ch in ch_unique:
            temp_list = []
            for file in files:
                if ch in file and ("tif" in file or "TIFF" in file or "tiff" in file):
                    temp_list.append(file)
            if " " in ch:
                ch = ch.replace(" ", "")
            for key, value in ch_dic.items():
                if key in ch:
                    df["FileName_" + value] = temp_list
                    df["PathName_" + value] = images_dir
                    file_width = temp_list[0]
                    path_width = images_dir
                    if illum_bool:
                        illum_temp = plate + "_Illum" + value + ".npy"
                        df["FileName_Illum" + value] = illum_temp
                        df["PathName_Illum" + value] = illum_dir

        # Process mask columns if required
        if include_masks:
            for index, row in df.iterrows():
                for mask_type, orig_channel in mask_channels.items():
                    # Ensure we have a corresponding column for this channel
                    file_name_column = f"FileName_{orig_channel}"
                    if file_name_column in df.columns:
                        if segmentation_method == "cellpose":
                            base_filename = row[file_name_column]
                            # Generate mask filename by replacing extension with '_cp_masks.png'
                            mask_filename = (
                                base_filename.replace(".tiff", "_cp_masks.png")
                                .replace(".TIFF", "_cp_masks.png")
                                .replace(".tif", "_cp_masks.png")
                            )
                            df.loc[index, f"FileName_{mask_type}"] = mask_filename
                            df.loc[index, f"PathName_{mask_type}"] = mask_output_dir
                        elif segmentation_method == "microsam":
                            base_filename = row[file_name_column]
                            # Generate mask filename by replacing extension with '.tif
                            mask_filename = (
                                base_filename.replace(".tiff", ".tif")
                                .replace(".TIFF", ".tif")
                                .replace(".tif", ".tif")
                            )
                            df.loc[index, f"ObjectsFileName_{mask_type}"] = (
                                mask_filename
                            )
                            df.loc[index, f"ObjectsPathName_{mask_type}"] = (
                                mask_output_dir
                            )

        # get wells and sites names
        wells = []
        sites = []
        for files in df.iloc[:, 0]:
            matches = re.search(regex, files)
            if not matches == None:
                wells.append(matches.group("Well"))
                sites.append(matches.group("Site"))
        df["Metadata_Well"] = wells
        df["Metadata_Site"] = sites
        df["Metadata_Plate"] = plate
        # save df
        if output_dir_bool:
            path = output_dir
            os.makedirs(path, exist_ok=True)
        else:
            directory = "load_data_csv"
            path = os.path.join(input_folder, directory)
            os.makedirs(path, exist_ok=True)
        if illum_bool:
            os.makedirs(cluster_illum_folder, exist_ok=True)
            illum_out = os.path.join(path, "load_data_with_illum.csv")
            df.to_csv(illum_out, index=False)
        else:
            loaddata_out = os.path.join(path, "load_data.csv")
            df.to_csv(loaddata_out, index=False)
            width = get_image_width(os.path.join(path_width, file_width), logger)
            df["Metadata_Width"] = width
            df = remove_path_cols(df, prefix="PathName_")
            representatives_out = os.path.join(
                path, "metadata_representative_cells.csv"
            )
            df.to_csv(representatives_out, index=False)


def get_folders_in_path(path):
    """
    Get all folders inside a directory
    """
    # List all directories in the provided path
    folders = [
        os.path.join(path, folder)
        for folder in os.listdir(path)
        if os.path.isdir(os.path.join(path, folder))
    ]
    print("found those folders", folders)
    return folders


def extract_plate_names(folders):
    """
    Extract plate names assuming that inside a folder, the name of the folders are the plate name. Save those and pass it to create_plate_dict.
    """
    plate_names = []
    pattern = re.compile(r".*[\\/](?P<Plate>.*)")
    for folder in folders:
        match = pattern.match(folder)
        if match:
            plate_names.append(match.group("Plate"))
            print(plate_names)
    return plate_names


def create_plate_dict(plate_names):
    """
    Create plate_dict when there is no links.sh file to get those plate names from.
    """
    plate_dict = {}
    for plate in plate_names:
        value = input(f"Enter value for {plate}: ")
        plate_dict[plate] = value
    return plate_dict
