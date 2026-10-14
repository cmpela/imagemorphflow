# imagemorphflow

[<a href="https://doi.org/10.5281/zenodo.23361703"><img src="https://zenodo.org/badge/1418538349.svg" alt="DOI"></a>
](https://zenodo.org/badge/1418538349.svg)

Python package for automating high-content screening image analysis workflows, from project setup and image organization to morphological profile processing.

`imagemorphflow` uses **CellProfiler 4.2.8** as its core image processing engine, with optional deep learning segmentation through **Cellpose** (via CellProfiler-plugins) or **micro-sam** (based on the Segment Anything Model). Package-specific code handles data ingestion, while **pycytominer** supports downstream annotation, normalization, and feature selection.

**Stable tested environment:** Ubuntu 22.04/24.04 (Linux). Windows users should use WSL2 for best compatibility.

## Workflow overview

The workflow begins by creating a named project, setting up its folder structure, and generating configuration files. Images can optionally be copied to local storage and are linked to the project using symbolic links.

Analysis follows a **plate-based approach**, where each plate corresponds to an acquisition folder in the microscope’s image storage.

## Configuration presets

The package supports the folder structures and image naming conventions of **ImageXpress** and **Endeavor** microscopes. Three configuration presets are available:

- **Cell Painting — ImageXpress:** channel configuration for the classical Cell Painting assay acquired on ImageXpress.
- **Cell Painting — Endeavor:** the corresponding configuration using Endeavor channel names.
- **Brightfield — Endeavor:** a brightfield configuration using channel `w5`.

For other assays, override the preset channel configuration by supplying the channels required for your analysis. For example, a nuclei-counting workflow can use only the nuclear channel.

## Features

- **CellProfiler integration:** Full pipeline automation for illumination correction, analysis, and profile generation
- **Cellpose support:** Integrated via [CellProfiler-plugins](https://github.com/CellProfiler/CellProfiler-plugins) - recommended for best results
- **micro-sam support:** For custom segmentation models - requires [fefossa/micro-sam](https://github.com/fefossa/micro-sam) with `loaddata_updated` branch
- **Project structure:** Standardized folder layout for organizing images, masks, and outputs
- **Plate management:** Automated symlink mapping and plate naming conventions
- **Echo file handling:** Convert and process liquid handler transfer files

## Installation

### Prerequisites

- **Operating System:** Ubuntu 22.04/24.04 (Linux) - **recommended**. For Windows, install [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) with Ubuntu.
- **CellProfiler 4.2.8** - See installation below
- **Python 3.9+**

### Step 1: Install CellProfiler

It's recommended to use conda to create a `cellprofiler4` environment, to allow better integration with this package. 

**For Cellpose integration (recommended):**

Follow the CellProfiler-plugins instructions:
```bash
git clone https://github.com/CellProfiler/CellProfiler-plugins.git
cd CellProfiler-plugins
# Follow their installation guide for CellPose support
```

**Basic CellProfiler installation:**
Follow the official instructions for your OS: https://github.com/CellProfiler/CellProfiler/wiki

### Step 2: Install imagemorphflow

```bash
# Clone this repository
git clone https://github.com/fefossa/imagemorphflow.git
cd imagemorphflow

# Create an environment using the yml file
conda env create -f environment.yml -n imagemorphflow

# Activate the env
conda activate imagemorphflow

# Install the imagemorphflow package
pip install -e .
```

### Optional: Install micro-sam (for custom segmentation)

To allow better integration with CellProfiler, we modified the code to generate masks that can be imported directly as objects.

```bash
# Clone my fork with loaddata_updated branch
git clone https://github.com/fefossa/micro-sam.git
cd micro-sam
git checkout loaddata_updated
pip install -e .
```

For Pycytominer:

```bash
git clone https://github.com/fefossa/pycytominer.git
cd pycytominer
git checkout issues/440
pip install -e .
```

## Usage

### Configuration

```bash
tmux new -s run
conda activate imagemorphflow

PROJECT_NAME=my_project
mkdir -p /home/$USER/projects/$PROJECT_NAME
```

#### Create manifest file

Create a manifest file (e.g., `my_project_manifest.json`):

```json
{
  "microscope": "imagexpress",
  "modality": "cellpainting",
  "mask_predict": false,
  "steps": ["analysis", "ingest", "join"],
  "join_profile": "basic",
  "overrides": {
    "project_name": "my_project",
    "image_path": "/path/to/image/folder",
    "symlinks_file": "my_project.json"
  }
}
```

**Microscope options:** `imagexpress`, `endeavor`

**Steps:** `illum`, `analysis`, `ingest`, `join`, `copy_to_scratch`, `predict_masks`

### Build configuration

```bash
imf build --manifest /home/$USER/projects/$PROJECT_NAME/my_project_manifest.json
```

### Run the pipeline

```bash
# Initialize project structure
imf run --script initialize_project_structure --config /home/$USER/projects/$PROJECT_NAME/workspace/configs/effective/latest_analysis.yaml

# Load data (creates symlinks)
imf run --script load_data --config /home/$USER/projects/$PROJECT_NAME/workspace/configs/effective/latest_analysis.yaml

# Predict masks (optional - if using micro-sam)
imf run --script predict_masks --config /path/to/config.yaml

# Run illumination pipeline
imf run --script run_cellprofiler --config /home/$USER/projects/$PROJECT_NAME/workspace/configs/effective/latest_illum.yaml

# Run analysis pipeline (after illumination completes)
imf run --script run_cellprofiler --config /home/$USER/projects/$PROJECT_NAME/workspace/configs/effective/latest_analysis.yaml

# Ingest profiles
imf run --script ingest_profiles --config /home/$USER/projects/$PROJECT_NAME/workspace/configs/effective/latest_ingest.yaml

# Join profiles
imf run --script join_profiles --config /home/$USER/projects/$PROJECT_NAME/workspace/configs/effective/latest_join.yaml
```

### Example Manifest Files

| File | Description |
|------|-------------|
| `example_manifest_full.json` | All options available for override |
| `example_manifest.json` | CellPainting/ImageXpress setup |

## Project Folder Structure

```
images/
├── images/     # Raw input images from microscope
├── illum/      # Illumination correction images
└── masks/      # Segmentation masks (CellPose or micro-sam output)

workspace/
├── analysis/       # Analysis pipeline outputs (parquet files)
├── backend/        # CellProfiler per-image outputs (txt files)
├── profiles/       # Joined population profiles (Results.tsv)
├── loaddata/       # Symlinks and metadata
├── logs/           # Pipeline execution logs
├── pipelines/      # CellProfiler .cppipe files
├── scripts/        # Custom scripts
├── symlinks/       # Symlink mapping JSON files
├── temp/           # Temporary files
└── tests/          # Test scripts
```

### Deep Learning Outputs

When using segmentation models:

```
workspace/deeplearning/
├── cellpose/   # CellPose model outputs and models
└── sam/        # micro-sam outputs and models
```

## Available Scripts

These are the stable scripts so far:

| Script | Description |
|--------|-------------|
| `initialize_project_structure` | Creates project folder structure and config |
| `load_data` | Creates image symlinks and plate mappings |
| `predict_masks` | Runs micro-sam or CellPose segmentation |
| `run_cellprofiler` | Runs illumination or analysis pipeline |
| `ingest_profiles` | Joins per-image data into database format |
| `join_profiles` | Combines all plates into final profiles |
| `copy_to_scratch` | Copies images to scratch space (if configured) |
| `plate_overview` | Generates plate overview images |

## Notes

- Use `tmux` to keep long-running jobs alive after disconnecting
- Check logs in `workspace/logs/` for debugging
- Mask prediction requires GPU for micro-sam
- Echo file conversion available via `convert_echo_files.py` utility

## Authors

Fernanda Garcia Fossa
