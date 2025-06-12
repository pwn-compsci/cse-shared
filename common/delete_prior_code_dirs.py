#! /usr/bin/env python3
import os
import json
import shutil

def delete_directories_with_entry(base_path, target_entry):
    # Walk through the directory
    for root, dirs, files in os.walk(base_path):
        for dir in dirs:
            entries_path = os.path.join(root, dir, 'entries.json')
            if os.path.exists(entries_path):
                try:
                    # Open and read the JSON file
                    with open(entries_path, 'r') as file:
                        data = json.load(file)
                        # Check if the target entry is in the resources
                        if any(target_entry in data.get('resource', '') for entry in data):
                            # Delete the directory
                            shutil.rmtree(os.path.join(root, dir))
                            print(f"Deleted directory: {os.path.join(root, dir)}")
                except Exception as e:
                    print(f"Error processing {entries_path}: {e}")

# Define the path and target entry
history_dir = '/home/hacker/.local/share/code-server/User/History'
target_resource_entry = ['cse240/05-mud/', 'cse240/06-mudshop','cse240/07-pokemud','cse240/09-scheme','cse240/10-prolog','cse240/44-revit-shiftit-groupit']

# Call the function
for tre in target_resource_entry:
    delete_directories_with_entry(history_dir, tre)

    base_dir = os.path.join("/home/hacker",tre)
    if os.path.exists(base_dir):
        shutil.rmtree(base_dir)
        print(f"Deleted base code dir: {base_dir}")
