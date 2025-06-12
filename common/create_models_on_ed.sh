#!/usr/bin/env bash

create_model_bad() { 
    # File to check for macro definitions
    file_path="/$1/model/main.c"

    # Regular expression pattern to match MODEL_BAD_X_Y
    pattern='MODEL_BAD_([0-9]+)_([0-9]+)_([0-9]+)'

    # Check if the file exists
    if [ -f "$file_path" ]; then  
        # Read the file line by line
        while IFS= read -r line; do
            echo $line
            if [[ $line =~ $pattern ]]; then
                # Extract X and Y from the matched pattern
                x="${BASH_REMATCH[1]}"
                y="${BASH_REMATCH[2]}"
                z="${BASH_REMATCH[3]}"
                # Define the output binary file name
                output_file="/$1/modelBad${x}.${y}.${z}.bin"

                # Compile the C program with the macro definition
                gcc -D "MODEL_BAD_${x}_${y}_${z}" -o "$output_file" "$file_path"

                if [ $? -ne 0 ]; then
                    gcc -D "MODEL_BAD_${x}_${y}_${z}" -o "$output_file" "$file_path" >> /challenge/errorlog &2>1
                    printf "\033[31mCompilation failed for macro MODEL_BAD_${x}_${y}_${z} \033[0m\n" >> /challenge/errorlog
                fi
                strip $output_file
                cp $output_file $clevel_work_dir
            fi
        done < "$file_path"
        
    fi 
}

create_model_bad $1


