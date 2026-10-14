from pathlib import Path
from imagemorphflow.utils import file_utils

source = Path("/home/fossa/projects/c2025_01/images/illum")

outfolder = "/home/fossa/projects/c2025_02/images/illum"

json_file = "/home/fossa/projects/c2025_02/workspace/symlinks/symlinks_masks.json"

file_utils.create_symlinks(source, json_file, outfolder)