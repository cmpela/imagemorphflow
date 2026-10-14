import os
from imagemorphflow.utils import metadata_utils, file_utils

wells = metadata_utils.plate_wells(plate_type=384, zero_pad=False)
sites = 4
subfolders = []

plates_symlinks = file_utils.load_symlink_mappings("/home/fossa/projects/g35/workspace/symlinks/2026_FDA_ALL.json")
input_folder = "/home/fossa/projects/g35/workspace/skeleton"

for plate_old, plate_new in plates_symlinks.items():
    for w in wells:
        for s in range(1, sites + 1):
            subf = f"{w}_{s}"
            path = os.path.join(input_folder, plate_new, subf)
            os.makedirs(path, exist_ok=True)