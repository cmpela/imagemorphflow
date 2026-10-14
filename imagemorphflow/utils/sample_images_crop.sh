#!/bin/bash

# Usage:
# sample_images_crop.sh SOURCE_DIR DEST_DIR PROJECT_NAME [OVERLAY ...]
#
# Examples:
# sample_images_crop.sh source destination insect
# sample_images_crop.sh source destination insect w5+w3
# sample_images_crop.sh source destination insect w5+w3 w5+w4
# sample_images_crop.sh source destination insect w5+w3+w1

set -e

if [ "$#" -lt 3 ]; then
    echo "Usage: $0 SOURCE_DIR DEST_DIR PROJECT_NAME [OVERLAY ...]"
    exit 1
fi

SRC_DIR=${1%/}
DEST_DIR=${2%/}
PROJECT_NAME=${3,,}

shift 3
OVERLAYS=("$@")

# Crop size relative to the previously generated representative image.
REFERENCE_SIZE=750
REFERENCE_CROP=200

# Original TIFF calibration. Cropping does not change the pixel size.
PIXEL_SIZE_UM=0.3318
SCALE_BAR_UM=20

# Scale bar appearance.
SCALE_BAR_MARGIN=15
SCALE_BAR_HEIGHT=5
SCALE_BAR_FONT_SIZE=16
SCALE_BAR_FONT="DejaVu-Sans"

# Convert the physical bar length to pixels, rounded to the nearest integer.
SCALE_BAR_PX=$(awk \
    -v bar_um="$SCALE_BAR_UM" \
    -v pixel_size="$PIXEL_SIZE_UM" \
    'BEGIN { printf "%.0f", bar_um / pixel_size }'
)

# Channel-specific contrast correction.
CORR=(x 16x22 12x14 30x22 25x32 25x22)

# Display colors for overlays.
CHANNEL_COLORS=(
    x
    "#ff0000"  # w1 - red
    "#ff8000"  # w2 - orange
    "#ffff00"  # w3 - yellow
    "#00ff00"  # w4 - green
    "#0000ff"  # w5 - blue
)

if [ -z "$SRC_DIR" ] || [ ! -d "$SRC_DIR" ]; then
    echo "Source directory does not exist: $SRC_DIR"
    exit 1
fi

if [ -z "$DEST_DIR" ] || [ ! -d "$DEST_DIR" ]; then
    echo "Destination directory does not exist: $DEST_DIR"
    exit 1
fi

# Validate overlay channel specifications.
for overlay_spec in "${OVERLAYS[@]}"; do
    if [[ ! "$overlay_spec" =~ ^w[1-5](\+w[1-5])*$ ]]; then
        echo "Invalid overlay specification: $overlay_spec"
        exit 1
    fi
done

mkdir -p "$DEST_DIR/images"

add_scale_bar() {
    local input_image="$1"
    local output_image="${input_image%.jpg}_scalebar.jpg"

    local image_width image_height
    local x_start x_end y_top y_bottom
    local label_height label_top

    read -r image_width image_height <<< "$(
        identify -format "%w %h" "$input_image"
    )"

    x_end=$((image_width - SCALE_BAR_MARGIN - 1))
    x_start=$((x_end - SCALE_BAR_PX + 1))

    y_bottom=$((image_height - SCALE_BAR_MARGIN - 1))
    y_top=$((y_bottom - SCALE_BAR_HEIGHT + 1))

    label_height=$((SCALE_BAR_FONT_SIZE + 10))
    label_top=$((y_top - label_height - 4))

    if (( x_start < SCALE_BAR_MARGIN || label_top < 0 )); then
        echo "Image is too small for the configured scale bar: $input_image"
        return 1
    fi

    convert "$input_image" \
        -gravity northwest \
        -fill white \
        -stroke none \
        -draw "rectangle ${x_start},${y_top} ${x_end},${y_bottom}" \
        \( \
            -size "${SCALE_BAR_PX}x${label_height}" \
            xc:none \
            -font "$SCALE_BAR_FONT" \
            -pointsize "$SCALE_BAR_FONT_SIZE" \
            -gravity center \
            -fill white \
            -stroke none \
            -annotate 0 "${SCALE_BAR_UM} µm" \
        \) \
        -gravity northwest \
        -geometry "+${x_start}+${label_top}" \
        -compose over \
        -composite \
        -quality 95 \
        "$output_image"
}

for row in {A..P}; do
    for col_no in {1..24}; do

        col=$(printf "%02d" "$col_no")
        well="${row}${col}"

        # Track crops generated during this run.
        generated_channels=()

        for w in {1..5}; do
            for f in "$SRC_DIR"/*/*/*"${well}_s5_w${w}"*.tif; do

                if [ -e "$f" ] && [[ "$f" != *_thumb* ]]; then

                    echo "Cropping ${well}, channel w${w} ..."

                    read -r width height <<< "$(
                        identify -format "%w %h" "$f"
                    )"

                    crop_width=$((width * REFERENCE_CROP / REFERENCE_SIZE))
                    crop_height=$((height * REFERENCE_CROP / REFERENCE_SIZE))

                    echo "Original: ${width}x${height}"
                    echo "Crop: ${crop_width}x${crop_height}"

                    crop_output="$DEST_DIR/images/${well}_w${w}_crop.jpg"

                    if [[ "$PROJECT_NAME" == "rpe1" && "$w" -eq 1 ]]; then

                        convert "$f" \
                            -gravity center \
                            -crop "${crop_width}x${crop_height}+0+0" \
                            +repage \
                            -level 0.6%,5% \
                            -quality 95 \
                            "$crop_output"

                    else

                        convert "$f" \
                            -gravity center \
                            -crop "${crop_width}x${crop_height}+0+0" \
                            +repage \
                            -sigmoidal-contrast "${CORR[$w]}" \
                            -level 1%,99.9% \
                            -quality 95 \
                            "$crop_output"

                    fi

                    generated_channels[$w]=1

                    # Save a separate annotated copy.
                    add_scale_bar "$crop_output"

                fi
            done
        done

        # Generate overlays from crops without scale bars.
        for overlay_spec in "${OVERLAYS[@]}"; do

            channel_string=${overlay_spec//w/}
            channel_string=${channel_string//+/ }

            read -ra channels <<< "$channel_string"

            overlay_scale=1.0

            # Reduce intensity only for five-channel overlays.
            if [ "${#channels[@]}" -eq 5 ]; then
                overlay_scale=0.6
            fi

            temp_layers=()
            missing_channel=false

            for w in "${channels[@]}"; do

                crop_input="$DEST_DIR/images/${well}_w${w}_crop.jpg"

                if [[ "${generated_channels[$w]:-0}" != 1 ]]; then
                    missing_channel=true
                    break
                fi

                temp_layer="$DEST_DIR/images/.${well}_w${w}_colored.png"

                convert "$crop_input" \
                    -colorspace Gray \
                    -evaluate multiply "$overlay_scale" \
                    +level-colors black,"${CHANNEL_COLORS[$w]}" \
                    "$temp_layer"

                temp_layers+=("$temp_layer")
            done

            if [ "$missing_channel" = true ]; then
                rm -f "${temp_layers[@]}"
                continue
            fi

            overlay_name=${overlay_spec//+/}
            overlay_output="$DEST_DIR/images/${well}_${overlay_name}_crop_overlay.jpg"

            echo "Creating overlay ${overlay_spec} for ${well} ..."

            cp "${temp_layers[0]}" \
                "$DEST_DIR/images/.${well}_overlay.png"

            for ((i = 1; i < ${#temp_layers[@]}; i++)); do

                convert \
                    "$DEST_DIR/images/.${well}_overlay.png" \
                    "${temp_layers[$i]}" \
                    -compose plus \
                    -composite \
                    "$DEST_DIR/images/.${well}_overlay_next.png"

                mv \
                    "$DEST_DIR/images/.${well}_overlay_next.png" \
                    "$DEST_DIR/images/.${well}_overlay.png"
            done

            convert \
                "$DEST_DIR/images/.${well}_overlay.png" \
                -quality 95 \
                "$overlay_output"

            # Add the scale bar after channel composition.
            add_scale_bar "$overlay_output"

            rm -f \
                "$DEST_DIR/images/.${well}_overlay.png" \
                "${temp_layers[@]}"
        done

    done
done