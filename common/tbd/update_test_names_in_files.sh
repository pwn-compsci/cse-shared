#!/bin/bash

# Check if the mandatory argument T is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <T>"
  exit 1
fi

T=$1

# Find all files in the subdirectory recursively
find . -type f | while read -r file; do
  # Create a temporary file for comparison
  temp_file=$(mktemp)
  
  # Use sed to replace testX.Y.json with testT.X.Y.json
  sed -E "s/test([0-9]+)\.([0-9]+)\.json/test$T.\1.\2.json/g" "$file" > "$temp_file"
  
  # Use sed to replace modelBadX.Y with modelBadT.X.Y if followed by space or .bin
  sed -E "s/modelBad([0-9]+)\.([0-9]+)([[:space:]]|\.bin)/modelBad$T.\1.\2\3/g" "$temp_file" > "${temp_file}.mod"
 
  # Use sed to replace MODEL_BAD_X_Y with MODEL_BAD_T_X_Y if followed by space or end of line
  #sed -E "s/MODEL_BAD_([0-9]+)_([0-9]+)([[:space:]]|$)/MODEL_BAD_$T_\1_\2\3/g" "${temp_file}.mod" > "${temp_file}.mod2"
  sed -E "s/MODEL_BAD_([0-9]+)_([0-9]+)([[:space:]]|$)/MODEL_BAD_${T}_\1_\2\3/g" "${temp_file}.mod" > "${temp_file}.mod2"
  
  grep -E "MODEL_BAD_.*([0-9]+)_([0-9]+)([[:space:]]|$)" $temp_file.mod2
 
  # Compare the original file with the modified file
  if ! cmp -s "$file" "${temp_file}.mod2"; then
    # If the files are different, move the modified file to the original file
    mv "${temp_file}.mod2" "$file"
    
    echo "Modified: $file"
  else
    # If the files are the same, remove the temporary files
    rm "${temp_file}.mod2"
  fi
  
  # Remove the temporary files
  rm "$temp_file" "${temp_file}.mod"
done