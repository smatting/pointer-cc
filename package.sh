#!/bin/bash

# Check if the correct number of arguments are provided
if [ "$#" -ne 4 ]; then
    echo "Usage: $0 <source_application_path> <destination_dmg_path> <volume_name> <background_image_path>"
    exit 1
fi

# Assigning command-line arguments to variables
source_application="$1"
destination_dmg="$2"
volume_name="$3"
background_image="$4"

# Create a temporary directory
temp_dir=$(mktemp -d)

# Create a symbolic link to the Applications directory
ln -s "/Applications" "$temp_dir/Applications"

cp -r "$source_application" "$temp_dir"

# # Resize the background image to match the desired window size
# background_resized="$temp_dir/background_resized.png"
# width=$(sips -g pixelWidth "$background_image" | grep -Eo "[0-9]+")
# height=$(sips -g pixelHeight "$background_image" | grep -Eo "[0-9]+")
# cp "$background_image" "$background_resized"
# hdiutil resize -size "${width}x${height}" "$background_resized" > /dev/null

# Create a read-only DMG with resized background image
# hdiutil create -srcfolder "$temp_dir" -volname "$volume_name" -format UDRW -ov -background "$background_resized" -fs HFS+ "$destination_dmg"
hdiutil create -srcfolder "$temp_dir" -volname "$volume_name" -format UDRW -ov -fs HFS+ "$destination_dmg"

# Cleanup: Remove the temporary directory
rm -rf "$temp_dir"

echo "DMG created successfully at: $destination_dmg"

