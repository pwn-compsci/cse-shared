#!/bin/bash

# Define the base target directory
target_base_dir="../../tests"

# Find and process symbolic links named like stestX.Y.json
find . -type l -name "stest*.json" | while read -r symlink; do
  # Extract the base name and directory of the symlink
  symlink_name=$(basename "$symlink")
  symlink_dir=$(dirname "$symlink")

  # Extract parts of the symlink name using regex
  if [[ "$symlink_name" =~ ^(stest)([0-9]+)\.([0-9]+)\.json$ ]]; then
    new_name="stest5.${BASH_REMATCH[2]}.${BASH_REMATCH[3]}.json"

    # Read the target of the symbolic link
    old_target=$(readlink "$symlink")

    # Construct the new target path
    new_target="${target_base_dir}/$new_name"

    # Remove the old symlink
    #echo rm "$symlink"

    # Create the new symbolic link with the new name and new target
    ln -s "$new_target" "$symlink_dir/$new_name"

    echo "Renamed $symlink_name to $new_target <- $symlink_dir/$new_name "
  fi
done
