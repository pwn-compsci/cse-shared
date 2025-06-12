#!/bin/bash
ADD_NUM=$1
if [[ -z "$ADD_NUM" ]]; then
    printf "ERROR, must provide new number to add \n"
    exit 99
fi 

# Find all files matching the pattern ?test*.json recursively
find . -type f -name '?test*.json' | while read file; do
    # Extract the directory and the filename
    dir=$(dirname "$file")
    filename=$(basename "$file")
    
    # Extract the part of the filename after the first character
    first_char=${filename:0:1}
    filename_part=${filename:1}
    
    # Check if the filename matches the pattern utestX.Y.json or stestX.Y.json
    if [[ $filename_part =~ ^test([0-9]+)\.([0-9]+)\.json$ && ($first_char == "u" || $first_char == "s") ]]; then
        X=${BASH_REMATCH[1]}
        Y=${BASH_REMATCH[2]}
        
        # Construct the new filename
        new_filename="${first_char}test$ADD_NUM.$X.$Y.json"
        
        # Construct the full path for the new file
        new_file="$dir/$new_filename"
        
        # Rename the file
        mv "$file" "$new_file"
        
        echo "Renamed $file to $new_file"
    else    
        echo "skipping $filename"
    fi
done