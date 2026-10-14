#!/bin/bash
# Usage: sample_images.sh SOURCE_DIR DEST_DIR PROJECT_NAME
set -e

SRC_DIR=${1%/}
DEST_DIR=${2%/}
PROJECT_NAME=${3,,}

# CORR=(x 20x22 20x22 10x15 20x32 20x32) #u2os
# CORR=(x 35x10 12x14 20x22 20x32 20x22) #rpe1
CORR=(x 16x22 12x14 30x22 25x32 25x22) #insect


if [ -z "$SRC_DIR" ] || [ ! -d "$SRC_DIR" ]; then
  echo Source Dir $SRC_DIR does not exist.
  exit 1
fi

if [ -z $DEST_DIR ] || [ ! -d $DEST_DIR ]; then
  echo Destination Dir $DEST_DIR does not exist.
  exit 1
fi

mkdir -p $DEST_DIR/images
for row in {A..P}; do
  for col_no in {1..24}; do
    col=$(printf "%02d" $col_no)
    # sample all images, incl. all controls
    # if [ $col -ne 11 -a $col -ne 12 ] || [ $row$col == H11 ]; then
    for w in {1..5}; do
      for f in "$SRC_DIR"/*/*/*$row${col}_s5_w$w*.tif; do
        if [ -e "$f" ] && [[ "$f" != *_thumb* ]]; then
          echo converting $PLATE : $row${col} channel $w ...
          echo ${CORR[$w]}
          set +e
          if [[ "$PROJECT_NAME" == "rpe1" && "$w" -eq 1 ]]; then
            convert "$f" \
              -resize 750x750 \
              -level 0.6%,5% \
              "$DEST_DIR/images/${row}${col}_w${w}.jpg" \
              > /dev/null
          else
            convert "$f" \
              -resize 750x750 \
              -sigmoidal-contrast "${CORR[$w]}" \
              -level 1%,99.9% \
              "$DEST_DIR/images/${row}${col}_w${w}.jpg" \
              > /dev/null
          fi
          set -e
        fi
      done
    done
    # fi
  done
done