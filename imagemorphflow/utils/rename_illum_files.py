import os

base_folder = "/home/fossa/projects/c2025_01/images/illum"

for subfolder in os.listdir(base_folder):
    subfolder_path = os.path.join(base_folder, subfolder)
    if os.path.isdir(subfolder_path):
        for filename in os.listdir(subfolder_path):
            if "Illum" in filename:
                new_filename = filename.replace("Illum", "IllumOrig")
                old_path = os.path.join(subfolder_path, filename)
                new_path = os.path.join(subfolder_path, new_filename)
                os.rename(old_path, new_path)
                print(f"Renamed: {filename} -> {new_filename} in {subfolder}")
