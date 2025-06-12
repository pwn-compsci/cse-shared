import os
import re

def rename_test_files_in_system_test_dirs():
    # Regular expression to match files starting with testX.Y.json
    pattern = re.compile(r'^test(\d+\.\d+)\.json$')
    
    # Walk through the current directory
    for root, dirs, files in os.walk('.'):
        if 'system_test' in root or 'user_test' in root:
            for file in files:
                if pattern.match(file):
                    old_file = os.path.join(root, file)
                    if 'system_test' in root:
                        new_file = os.path.join(root, f's{file}')
                    else:
                        new_file = os.path.join(root, f'u{file}')
                    # Rename the file
                    os.rename(old_file, new_file)
                    print(f"Renamed: {old_file} -> {new_file}")

# Run the function
rename_test_files_in_system_test_dirs()
