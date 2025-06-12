#!/bin/bash

# Directory to search for files
search_dir="."

# Find and process each file matching the pattern
find "$search_dir" -type f -name "test*.json" | while read -r file; do
  # Extract the base name of the file
  file_name=$(basename "$file")
  
  # Extract the version number from the file name
  version=$(echo "$file_name" | grep -oP '\d+\.\d+')
  
  # Create the new file name
  new_file_name="stest5.$version.json"
  
  # Get the directory of the current file
  file_dir=$(dirname "$file")
  
  # Construct the new file path
  new_file_path="$file_dir/$new_file_name"
  
  # Rename the file
  mv "$file" "$new_file_path"
  
  echo "Renamed file: $file -> $new_file_path"
done
