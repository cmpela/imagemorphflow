#!/usr/bin/env bash
# Rename and gather PNGs from immediate subfolders into a central folder.
# Usage:
#   ./rename_pl_overview.sh /path/to/plates
#   ./rename_pl_overview.sh /path/to/plates /path/to/dest

# Be strict with unset vars; don't exit on first error so we can continue.
set -u
IFS=$'\n\t'
shopt -s nullglob dotglob

# --- parse args ---
BASE="${1:-}"
DEST="${2:-}"

if [[ -z "${BASE}" ]]; then
  echo "Usage: $0 BASE_DIR [DEST_DIR]"
  exit 2
fi

# Normalize paths
BASE="$(readlink -f "${BASE}")" || { echo "Invalid BASE: ${BASE}"; exit 1; }
if [[ -z "${DEST}" ]]; then
  DEST="${BASE}/ALL_PNGs"
fi
DEST="$(readlink -f "$(mkdir -p "${DEST}" && echo "${DEST}")")"

# Safety: ensure BASE exists and is a dir
if [[ ! -d "${BASE}" ]]; then
  echo "Error: BASE directory not found: ${BASE}"
  exit 1
fi

moved=0
skipped=0

echo "BASE: ${BASE}"
echo "DEST: ${DEST}"

# Iterate only immediate subdirectories of BASE, excluding DEST itself
while IFS= read -r -d '' folder; do
  # Skip DEST if it's inside BASE
  [[ "${folder}" == "${DEST}" ]] && continue

  folder_name="$(basename "${folder}")"
  echo ">> Processing folder: ${folder_name}"

  # Find PNGs (case-insensitive) directly in the subfolder
  while IFS= read -r -d '' file; do
    filename="$(basename "${file}")"
    target="${DEST}/${folder_name}_${filename}"

    # Avoid collisions by adding a numeric suffix
    if [[ -e "${target}" ]]; then
      i=1
      while [[ -e "${DEST}/${folder_name}_${i}_${filename}" ]]; do
        ((i++))
      done
      target="${DEST}/${folder_name}_${i}_${filename}"
    fi

    if mv -- "${file}" "${target}"; then
      ((moved++))
    else
      echo "WARN: failed to move: ${file}"
      ((skipped++))
    fi
  done < <(find "${folder}" -maxdepth 1 -type f \( -iname '*.png' \) -print0)

done < <(find "${BASE}" -mindepth 1 -maxdepth 1 -type d -print0)

echo "Done. Moved: ${moved}. Skipped: ${skipped}. Output dir: ${DEST}"
