#!/bin/bash

# Get the path of the script
script_dir=$(dirname "$(realpath "$0")")

# Create a temporary directory for staging
tmp_dir=$(mktemp -d)
echo "Using temporary directory $tmp_dir for staging..."

# Find all 'group_template' and 'system_tests' directories and restructure them
find . -type d \( -path '*/lab-??-??/group_template' -o -path '*/lab-??-??/system_tests' -o -path '*/lab-??-??/.config' \) | while read dir; do
    # Extract the grouplab?? part and the specific folder name
    grouplab_dir=$(echo "$dir" | grep -o './grouplab[0-9][0-9]')
    folder_name=$(basename "$dir")
    
    # Create corresponding directory structure in temporary directory
    mkdir -p "$tmp_dir/$grouplab_dir/$folder_name"

    # Copy contents to the temporary directory
    echo cp -r "$dir/"* "$tmp_dir/$grouplab_dir/$folder_name/"
    cp -r "$dir/"* "$tmp_dir/$grouplab_dir/$folder_name/"
done

# Navigate to the temporary directory
cd "$tmp_dir"

echo $script_dir
# Create the tarball from the temporary directory, placing it in the parent directory of the script path
echo tar -czf "$script_dir/../grouplabs.tar.gz" ./*
tar -czf "$script_dir/../grouplabs.tar.gz" ./*

# Clean up the temporary directory
rm -rf "$tmp_dir"
echo "Cleanup complete. Temporary files removed."
cd -

tmp_dir=$(mktemp -d)
echo "Using temporary directory $tmp_dir for staging..."

# Find all 'group_template' and 'system_tests' directories and restructure them
find . -type d \( -path '*/lab-??-??/model' \) | while read dir; do
    # Extract the grouplab?? part and the specific folder name
    grouplab_dir=$(echo "$dir" | grep -o './grouplab[0-9][0-9]')
    folder_name=$(basename "$dir")
    
    # Create corresponding directory structure in temporary directory
    mkdir -p "$tmp_dir/$grouplab_dir/$folder_name"

    # Copy contents to the temporary directory
    cp -r "$dir/"* "$tmp_dir/$grouplab_dir/$folder_name/"
done

# Navigate to the temporary directory
cd "$tmp_dir"

echo $script_dir
# Create the tarball from the temporary directory, placing it in the parent directory of the script path
tar -czf "$script_dir/../grouplab_models.tar.gz" ./*

# Clean up the temporary directory
rm -rf "$tmp_dir"
echo "Cleanup complete. Temporary files removed."

echo "Tarball created at grouplabs.tar.gz"
