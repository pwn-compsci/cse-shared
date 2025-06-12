#!/usr/bin/exec-suid -- /usr/bin/python3

import os
import re
import sys 
import json
from pathlib import Path
import difflib
from datetime import datetime, timedelta
import argparse 
import subprocess 
import base64 

# Get the current EUID
current_euid = os.geteuid()

# Set the EUID to 1000 for hacker
new_euid = 1000
os.seteuid(new_euid)

# Directory paths
coders_work_dir = os.getenv('clevel_work_dir')
vscode_history_dir = Path("/home/hacker/.local/share/code-server/User/History")
extension_log_file = Path("/home/hacker/cse240/.vscode/cp.dat")
report_output_dir = f"/home/me/tmp/"
basedir = ""
pid=""

def get_modified_time(file_path):
        return os.path.getmtime(file_path)

def check_and_append_pid(pid, file_path="/home/hacker/cse240/.cse240env"):
    pid_str = f"vsnum={pid}"

    # Check if file exists, if not create an empty one
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            pass

    # Read the file and check if pid_str is already present
    with open(file_path, 'r') as f:
        lines = f.readlines()
        if pid_str in lines:
            return

    # Append pid_str to the file if not found
    with open(file_path, 'a') as f:
        f.write(f"{pid_str}\n")

def find_vsnum(file_path="/home/hacker/cse240/.cse240env"):
    # Check if the file exists
    if not os.path.exists(file_path):
        return ""

    # Search for the 'vsnum' field in the file
    with open(file_path, 'r') as f:
        for line in f:
            if line.startswith("vsnum="):
                vsnum_value = line.strip().split("=")[1]  # Extract the value after 'vsnum='
                return vsnum_value

    return ""


def get_file_paths(base_dir):
    prefix_to_remove = os.path.abspath(os.path.join(base_dir, os.pardir, os.pardir))
    
    # Walk through all directories and files in base_dir
    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if file.endswith(('.c', '.cpp')):
                # Full path of the file
                full_path = os.path.join(root, file)
                # Remove the specified prefix and normalize the path
                relative_path = os.path.normpath(full_path.replace(prefix_to_remove, ''))
                #print(f"{relative_path}, {os.path.join(full_path)}")
                yield relative_path, os.path.join(full_path)
    
def count_deactivations():
    deactivate_old = "The pwn Extension was disabled".encode('utf-8')
    #deactivate_newer = "The pwn extension was deactivated at".encode('utf-8')
    encoded_old = base64.b64encode(deactivate_old).decode('utf-8')
    #encode_newer = base64.b64encode(deactivate_newer).decode('utf-8')
    
    found_cnt = 0
    with open(extension_log_file, "r") as rf:
        lines = rf.readlines()
    for l in lines:
        if l.startswith(encoded_old):
            found_cnt += 1
    if found_cnt < 3:
        return ""
    return f"\tWARN: \033[38;5;202mExtension disabled {found_cnt} times \033[0m"

def find_entries_json_with_file(file_path):
    # Search for entries.json files under all subdirectories of vscode_history_dir
    for root, dirs, files in os.walk(vscode_history_dir):
        if "entries.json" in files:
            entries_file = Path(root) / "entries.json"
            # Open the entries.json file and look for the file_path within its entries
            try:
                with open(entries_file, 'r') as f:
                    data = json.load(f)
                res = data.get("resource","")
                if res.endswith(file_path):
                    # Check if any entry matches the file_path
                    return entries_file, data.get("entries",[])
            except Exception as e:
                print(f"Error reading {entries_file}: {e}")
                continue
    return None, None

def file_content(path):
    with open(path, 'r', encoding='utf-8') as file:
        return file.readlines()

def find_added_lines(old_lines, new_lines):
    s = difflib.SequenceMatcher(None, old_lines, new_lines)
    added_lines = []
    for tag, i1, i2, j1, j2 in s.get_opcodes():
        if tag == 'insert':  # Lines added in new file
            added_lines.extend(new_lines[j1:j2])
    return added_lines

def ignore_existing_content(added_lines, old_lines, diff):
    found = 0
    total = 0
    old_text = ''.join(old_lines)
    for line in added_lines:
        stripped_line = line.strip()
        if (len(stripped_line)) == 0:
            continue 
        if stripped_line in old_text:
            found += len(line)

        total +=len(line)
    
    if total == 0:
        return True 

    #print (f"{found=} {total=} {total - found=}\n")

    return total - found 

def calculate_time_spent(files_mod_times):
    # Sort files by modification time
    files_mod_times.sort(key=lambda x: x[1])

    total_time = timedelta(0)
    previous_time = None

    for file, mod_time in files_mod_times:
        current_time = mod_time

        if previous_time and (current_time - previous_time <= timedelta(minutes=5)):
            total_time += current_time - previous_time
        
        previous_time = current_time
    total_hours = total_time.total_seconds() / 3600
    return total_hours

def analyze_vscode_history(file_path, absolute_file_path, all_diffs=False):
    REPORT_PERCENT_THRESHOLD = .25
    large_message = ""

    entries_file, entries = find_entries_json_with_file(file_path)
    if not entries_file or not entries:
        #print(f"No VSCode history found for {file_path}")
        return None 

    version_count = len(entries)
    
    timestamps = [(entry["id"], datetime.fromtimestamp(entry['timestamp']/1000)) for entry in entries if ".json" not in entry['id'] and "_" not in entry["id"]]
    
    #time_spent = (max(timestamps) - min(timestamps)).total_seconds() / 3600 if len(timestamps) > 1 else 0

    #files_mod_times = get_file_modification_times(base_directory)    
    time_spent = calculate_time_spent(timestamps)

    # Assuming 'entries' is a list of dictionaries where each dictionary has a 'timestamp' key
    sorted_entries = sorted(entries, key=lambda entry: entry['timestamp'])
    
    if all_diffs:
        print(f"{absolute_file_path}: {version_count} versions, {time_spent:.2f} hours worked", end=" ")

    largest_diff = 0
    previous_size = None
    dirname = None 
    file_size_of_largest_diff = 0
    largest_diff_prec=""
    large_changes=[]
    td = []
    for entry in sorted_entries:
        version_file = Path(entries_file.parent) / entry['id']
        if version_file.exists():
            file_size = version_file.stat().st_size
            if previous_size is not None:
                diff = abs(file_size - previous_size)
                larger_size = max(file_size, previous_size)

                f1time = os.path.getmtime(prev_file_path)            
                f2time = os.path.getmtime(version_file)      
                time_difference = abs(f1time - f2time)
                #print(f"DIFF TESTING: {diff} {larger_size} {(larger_size*REPORT_PERCENT_THRESHOLD)} {time_difference:.0f}")
                if diff > largest_diff:
                    largest_diff = diff
                    largest_diff_prec = f"{diff/larger_size*100:.0f}%"
                    file_size_of_largest_diff= larger_size
                    largest_diff_files = (prev_file_path, version_file)  # Store the paths of the two versions                    
                
                # if time difference is a bit longer between 3 minutes and 6 minutes then set 
                # diff threshold to 600 else set to default of 400
                threshold = 600 if 180 < time_difference < 360 else 400
                
                if diff > threshold :                    
                    old_lines = file_content(prev_file_path) if prev_file_path else []
                    new_lines = file_content(version_file)

                    added_lines = find_added_lines(old_lines, new_lines)
                    #print(f"{diff} {prev_file_path=} {version_file=}")

                    # reduce diff by content pasted from prior file to the current file (self file copy shouldn't be counted)
                    diff = ignore_existing_content(added_lines, old_lines, diff)                        
                    
                    if diff > threshold :
                        large_changes.append([prev_file_path, version_file, diff, larger_size, time_difference])
        
                if all_diffs:
                    print("v"*80)
                    subprocess.run(["icdiff", prev_file_path, version_file])
                    print("^"*80)
            
            previous_size = file_size
            prev_file_path = version_file 
       
        if dirname is None:
            dirname = os.path.dirname(version_file)
    
    large_count = len(large_changes)
    
    if not all_diffs:
        
        largest_diff_info = f" Largest diff: {largest_diff} bytes ({largest_diff_prec})"
        
        if large_count > 3:
            #print_out = [f"{chg[2]}b" if chg[2] > 500 else f"{chg[2]/chg[3]*100:.0f}% in {chg[4]:.0f}s" for chg in large_changes]
            print_out = [f"{chg[2]}b in {chg[4]:.0f}s" for chg in large_changes]

            large_message += f"\t\tWARN: \033[38;5;11m {large_count} diffs exceed threashold {print_out} \033[0m details at diffs/{pid}_{sid}_{os.path.basename(file_path)}.diff"
            
            output_file_path=f"{report_output_dir}/diffs/{pid}_{sid}_{os.path.basename(file_path)}.diff"
            
            with open(output_file_path, 'w') as output_file:
                # Run the command and capture both stdout and stderr            
                for chg in large_changes:
                    output_file.write(f"***** {chg} *****\n")
                    command = ["icdiff", chg[0], chg[1]]
                    result = subprocess.run(command, stdout=output_file, stderr=subprocess.STDOUT)

        
    return {"vsc_hist_dir": dirname, "large_count": large_count, "version_count": version_count, "time_spent": time_spent, "largest_diff_info": largest_diff_info, "large_message": large_message }

def find_big_paste(directory_path):
    files = [os.path.join(directory_path, f) for f in os.listdir(directory_path) 
             if os.path.isfile(os.path.join(directory_path, f)) and 
             (f.startswith('tN') or f.startswith('tB') or f.startswith('tNB') or 
              f.startswith('cpN') or f.startswith('cpB') or f.startswith('cpNB')) and "_" in f]
    #files.sort(key=get_modified_time)
    big_paste = ""    
    results = []
    for i in range(0, len(files)):

        pastefile = Path(files[i])
        if pastefile.exists():
            paste_size = pastefile.stat().st_size
            results.append(f"{os.path.basename(files[i])} ({paste_size}b)")
    
    if len(results) > 0:
        big_paste = "\t\tWARN: \033[38;5;202mFound Large pastes from external source " + ",".join(results) + "\033[0m"
    
    return big_paste

def max_numerical_subdir(base_dir):
    # List all entries in the directory
    entries = os.listdir(base_dir)
    
    # Filter entries to include only numeric directories
    numeric_dirs = [entry for entry in entries if entry.isdigit() and os.path.isdir(os.path.join(base_dir, entry))]
    
    # Convert the directory names to integers
    numeric_dirs = [int(dir_name) for dir_name in numeric_dirs]
    
    # Find the maximum directory number
    if numeric_dirs:  # Make sure there are any numeric directories found
        max_dir = max(numeric_dirs)
        return f"{max_dir:02}"  # Return as two-digit string, consistent with your format
    else:
        return None  # Return None if no numeric directories are found

def get_prior_level_path(path):
    # Regular expression to find the "0X" part
    match = re.search(r'(\d{2})-(\w+)/0(\d+)', path)
    if match:
        # Extract the components of the path
        chapter = match.group(1)  # e.g., '06'
        directory = match.group(2)  # e.g., 'mudshop'
        number = int(match.group(3))  # Convert X to integer

        # Decrement the number, ensure it stays above zero
        new_number = max(1, number - 1)

        # Rebuild the path with the new number
        new_path = path[:match.start(3)] + f"{new_number}" + path[match.end(3):]
        return new_path
    else:
        # If no match, return the original path
        return path

def get_last_level_equiv_file(abs_file_path):

    if "05-mud" in abs_file_path:
        if "05-mud/01" not in abs_file_path: # avoid first level file
            prior_level_file_path = get_prior_level_path(abs_file_path)
            #print (f"{prior_level_file_path=}")
            if (os.path.exists(prior_level_file_path)):
                return prior_level_file_path
    
    if "06-mudshop" in abs_file_path:
        if "06-mudshop/01" in abs_file_path: # get from prior project
            abs_filename = os.path.basename(abs_file_path).replace("cpp", "c")
            prior_project_path = os.path.dirname(abs_file_path).replace("06-mudshop/01", "05-mud")
            max_dir = max_numerical_subdir(prior_project_path)
            prior_project_path = os.path.join(prior_project_path, max_dir, abs_filename)
            if (os.path.exists(prior_project_path)):
                return prior_project_path
        else:
            prior_level_file_path = get_prior_level_path(abs_file_path)
            #print (f"{prior_level_file_path=}")
            if (os.path.exists(prior_level_file_path)):
                return prior_level_file_path

    return None 

def analyze_diff_first_history_and_last_level(vsc_history_dir, abs_file_path, pid):
    sig_change_message = ""
    files = [os.path.join(vsc_history_dir, f) for f in os.listdir(vsc_history_dir) 
             if os.path.isfile(os.path.join(vsc_history_dir, f)) and (f.endswith('.c') or f.endswith('.cpp')) and ("_" not in f)] # if includes _ then is inserted text or detected external paste
    files.sort(key=get_modified_time)
    significant_change_count  = 0
    big_change_files = []

    earliest_file_version = files[0]

    last_level_file_path = get_last_level_equiv_file(abs_file_path)

    if last_level_file_path is not None:
        prev_file = last_level_file_path
        curr_file = earliest_file_version
        similarity_ratio = files_significantly_changed(prev_file, curr_file)
        #print(f"{(prev_file, curr_file, similarity_ratio)}")
        if similarity_ratio < .6:
            prev_size = os.path.getsize(prev_file)
            curr_size = os.path.getsize(curr_file)
            size_difference = abs(prev_size - curr_size)
            percent_size_diff = size_difference / max(prev_size, curr_size) * 100
            
            if prev_size > 500 and curr_size > 500:
                sig_change_message = f"\t\tWARN: \033[38;5;11mFirst history file {os.path.basename(curr_file)} ({curr_size/1000:.1f}k) differs significantly from last file in prior level ({prev_file}) ({prev_size/1000:.1f}k) similarity={similarity_ratio:.3f} size diff={size_difference/1000:.1f}k ({percent_size_diff:.0f}%) \033[0m \n"
                if len(pid) > 0:
                    last_dir = os.path.basename(os.path.dirname(prev_file))
                    next_to_last_dir = os.path.basename(os.path.dirname(os.path.dirname(prev_file)))
                    sig_change_message += f"\t\t\ticdiff {basedir}/{pid}_history/{os.path.basename(os.path.dirname(curr_file))}/{os.path.basename(curr_file)} {basedir}/{pid}_code_cse240/{next_to_last_dir}/{last_dir}/{os.path.basename(prev_file)} "
                else:
                    sig_change_message += f"\t\t\ticdiff {curr_file} {prev_file} "
            
    return sig_change_message


def parse_bytes_value(byte_string):
    # Extract the numerical part from a string like '26b'
    return int(byte_string.strip('b'))

def extract_key_logs(file_path, start_time, end_time):
    total_bytes = 0
    with open(file_path, 'r') as file:
        for line in file:
            parts = line.split(': ')
            timestamp_str = parts[0]
            byte_value_str = parts[1].split(' ')[0]

            # Convert timestamp string to a datetime object
            timestamp = datetime.datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S.%fZ')
            # Convert times from getmtime to datetime
            start_datetime = datetime.datetime.fromtimestamp(start_time)
            end_datetime = datetime.datetime.fromtimestamp(end_time)

            # Check if the timestamp is within the specified range
            if start_datetime <= timestamp <= end_datetime:
                # Parse the byte value and add to total
                total_bytes += parse_bytes_value(byte_value_str)

    return total_bytes

def crazy_growth_count(vsc_hist_dir):
    sig_change_message = ""
    files = [os.path.join(vsc_hist_dir, f) for f in os.listdir(vsc_hist_dir) 
             if os.path.isfile(os.path.join(vsc_hist_dir, f)) and (f.endswith('.c') or f.endswith('.cpp')) and ("_" not in f)] # if includes _ then is inserted text or detected external paste
    files.sort(key=get_modified_time)
    
    found_increase = 0
    qualifying_file_compare = 0
    threshold_activity_rate = 180/60 # assuming upper limit of 180 characters per minute / 60
    total_time = 0
    total_bytes = 0

    for i in range(1, len(files)):
        prev_file = files[i - 1]
        curr_file = files[i]        
        prev_size = os.path.getsize(prev_file)
        curr_size = os.path.getsize(curr_file)
        size_diff  = curr_size - prev_size
        f1time = os.path.getmtime(prev_file)            
        f2time = os.path.getmtime(curr_file)      
        time_difference = abs(f1time - f2time)
        if time_difference > 300:
            continue 
        if size_diff < 50:
            continue 
        if curr_size > prev_size:
            activity_rate = (curr_size-prev_size) / time_difference
            total_bytes += (curr_size-prev_size) 
            total_time += time_difference
            #print(f"{prev_file}\t{curr_file}\t {f1time} {f2time} {time_difference:.2f} {(curr_size-prev_size)}b {activity_rate:.1f} tots=> {total_bytes:.1f} {total_time} {total_bytes/total_time*60:.1f}")
            if activity_rate > threshold_activity_rate:
                found_increase += 1
            qualifying_file_compare += 1
    
    if total_time > 0:
        additions_per_minute = total_bytes/total_time*60
        
        if found_increase > 5 or additions_per_minute > 1000:
            if additions_per_minute > 400 and found_increase > 5:
                return additions_per_minute, f"\t\tWARN: \033[38;5;202m{found_increase} history files grew too fast, avg {additions_per_minute:.1f} bpm, grew {total_bytes}b over {total_time/60:.1f}m (total files measured: {qualifying_file_compare}) \033[0m"
            else:
                return additions_per_minute, f"\t\tWARN: \033[38;5;11m{found_increase} history files pretty fast, avg {additions_per_minute:.1f} bpm, grew {total_bytes}b over {total_time/60:.1f}s (total files measured: {qualifying_file_compare})\033[0m"
    
    return 0, ""

def detect_line_changes(old_version, new_version):
    import re
    from difflib import Differ

    def normalize_code(lines):
        # Normalize braces by ensuring they appear on a new line and standardize indentation
        normalized_lines = []
        for line in lines:
            # Remove all leading/trailing whitespace and reduce multiple spaces to one
            stripped_line = re.sub(r'\s+', ' ', line.strip())
            # Move opening braces to a new line if not already
            if '{' in stripped_line and not stripped_line.startswith('{'):
                parts = stripped_line.split('{')
                normalized_lines.append(parts[0].strip())
                normalized_lines.append('{' + parts[1] if len(parts) > 1 else '{')
            else:
                normalized_lines.append(stripped_line)
        return normalized_lines

    # Normalize both old and new versions before comparing
    old_lines = normalize_code(old_version.splitlines(keepends=False))
    new_lines = normalize_code(new_version.splitlines(keepends=False))

    d = Differ()
    diff = list(d.compare(old_lines, new_lines))
    
    added = sum(1 for x in diff if x.startswith('+ '))
    deleted = sum(1 for x in diff if x.startswith('- '))
    total_lines_old = len(old_lines)
    total_lines_new = len(new_lines)

    # Estimate total changes by considering lines added to and deleted from the original
    total_changes = added + deleted
    total_lines_estimate = max(total_lines_old, total_lines_new)
    percent_changed = (total_changes / total_lines_estimate) * 100 if total_lines_estimate > 0 else 0

    return {
        'added': added,
        'deleted': deleted,
        'total_lines_old': total_lines_old,
        'total_lines_new': total_lines_new,
        'percent_changed': percent_changed
    }


def analyze_line_changes(directory_path):
    sig_change_message = ""
    files = [os.path.join(directory_path, f) for f in os.listdir(directory_path) 
             if os.path.isfile(os.path.join(directory_path, f)) and (f.endswith('.c') or f.endswith('.cpp')) and ("_" not in f)] # if includes _ then is inserted text or detected external paste
    files.sort(key=get_modified_time)

    
    for i in range(1, len(files)):
        prev_file = files[i - 1]
        curr_file = files[i]
        prev_size = os.path.getsize(prev_file)
        curr_size = os.path.getsize(curr_file)
        f1time = os.path.getmtime(prev_file)            
        f2time = os.path.getmtime(curr_file)      

        with open(prev_file, "r") as rf:
            prev_file_contents = rf.read()
        with open(curr_file, "r") as rf:
            curr_file_contents = rf.read()

        line_change = detect_line_changes(prev_file_contents, curr_file_contents)    
        
        if line_change["added"] > 50 or line_change["deleted"] > 75:
            time_diff = f2time-f1time
            size_diff = abs(curr_size-prev_size)
            print(f"{line_change} {time_diff:.1f}s {size_diff:.1f}b {size_diff/time_diff:.1f}")
            print(f"\t\t\ticdiff {prev_file} {curr_file}")

def analyze_for_significant_changes(directory_path, pid):
    sig_change_message = ""
    files = [os.path.join(directory_path, f) for f in os.listdir(directory_path) 
             if os.path.isfile(os.path.join(directory_path, f)) and (f.endswith('.c') or f.endswith('.cpp')) and ("_" not in f)] # if includes _ then is inserted text or detected external paste
    files.sort(key=get_modified_time)
    significant_change_count  = 0
    big_change_files = []
    
    for i in range(1, len(files)):
        prev_file = files[i - 1]
        curr_file = files[i]
        similarity_ratio = files_significantly_changed(prev_file, curr_file)
        prev_size = os.path.getsize(prev_file)
        curr_size = os.path.getsize(curr_file)
        #print(f"{(prev_file, curr_file, similarity_ratio)}")
        if similarity_ratio < .5 and max(prev_size, curr_size) > 400:
            f1time = os.path.getmtime(prev_file)            
            f2time = os.path.getmtime(curr_file)      
            time_difference = abs(f1time - f2time)
            if time_difference < 300:
                significant_change_count += 1
                big_change_files.append((prev_file, curr_file, similarity_ratio))

    if significant_change_count > 3:
        first_f1,_,_ = big_change_files[0]
        sig_change_message += f"\t\tWARN: \033[38;5;11m{significant_change_count} history files had significant changes in {os.path.basename(os.path.dirname(first_f1))} was \033[0m"
        for f1, f2, similarity_ratio in big_change_files:
            f1time = os.path.getmtime(f1)            
            f2time = os.path.getmtime(f2)      
            time_difference = abs(f1time - f2time)
            f1_size = os.path.getsize(f1)
            f2_size = os.path.getsize(f2)        
            # Calculate the absolute difference in file sizes
            size_difference = abs(f1_size - f2_size)
            percent_diff = size_difference / max(f1_size, f2_size) * 100
            run_diff = ""
            if len(pid) > 0:
                run_diff = f"  icdiff {basedir}/{pid}_history/{os.path.basename(os.path.dirname(f1))}/{os.path.basename(f1)} {basedir}/{pid}_history/{os.path.basename(os.path.dirname(f2))}/{os.path.basename(f2)} "
            else:
                run_diff = f"  icdiff {f1} {f2}"
            sig_change_message += f"\n\t\t\t{os.path.basename(f1)} ({f1_size/1000:.1f}k) v. {os.path.basename(f2)} ({f2_size/1000:.1f}k) ::> sim={similarity_ratio:.3f} time diff={time_difference:.0f}s size diff={size_difference}b ({percent_diff:.0f}%) {run_diff}" 

            #print(f"\t\ticdiff {f1} {f2}")

    return sig_change_message    

def files_significantly_changed(file1_path, file2_path, threshold=0.6):
    
    with open(file1_path, 'r') as file1, open(file2_path, 'r') as file2:
        file1_lines = file1.readlines()
        file2_lines = file2.readlines()

        # Use difflib to compute a similarity ratio
        diff = difflib.SequenceMatcher(None, file1_lines, file2_lines)
        similarity_ratio = diff.ratio()
        
        # if similarity_ratio < threshold:
        #     print(f"icdiff {file1_path} {file2_path} ")
        #     print(f"difference: {similarity_ratio}")
        # If similarity ratio is lower than the threshold, consider the files significantly different
        return similarity_ratio 

def get_oldest_c_cpp_file_size(directory_path):
    # Function to get the creation or modified time of a file
    def get_creation_time(file_path):
        return os.path.getmtime(file_path)  

    # Get a list of .c and .cpp files in the directory
    files = [os.path.join(directory_path, f) for f in os.listdir(directory_path) 
             if os.path.isfile(os.path.join(directory_path, f)) and (f.endswith('.c') or f.endswith('.cpp')) and ("_" not in f)]

    if not files:
        return "", 0
    
    # Find the oldest file by sorting based on creation time
    oldest_file = min(files, key=get_creation_time)
    
    # Get the file size of the oldest file
    file_size = os.path.getsize(oldest_file)

    # Return the file size and the file name
    return oldest_file, file_size

import os
import difflib
from pathlib import Path
import time

def pill_search(fullpath, vsc_hist_dir):
    search_keys = ["super-duper scanf completed sir","getchar for the win", "b64SubEncoder", "override by extra string", "concatEnder", "puts(\"That's all for katkat", "Now with Even More MUD", "checkCounter", "checking arguments for generating tests", "arg_cnt", "arg_vals", "load_json_items function is done via filename","extra attempt to validate items", "MAX_JSON","Loader is off to left", "SSBhbSB2aW9s","the shop entry starts up the shop interface", "secondStoreEntry","Pokemud is too much pokefun","Pokémud is too much pokéfun", "getMove completed", "Wow, that was a great addition", "Directions to your desired location discovered"]
    
    with open(fullpath, "r") as rf:
        lines = rf.readlines()
        for l in lines:
            for sk in search_keys:
                if sk in l:
                    return f"\t\tALERT: \033[48;5;1m\033[38;5;226mFound the pill '{sk}' in the submitted file {fullpath} \033[0m"
    
    files = [os.path.join(vsc_hist_dir, f) for f in os.listdir(vsc_hist_dir) 
             if os.path.isfile(os.path.join(vsc_hist_dir, f)) and (f.endswith('.c') or f.endswith('.cpp')) and ("_" not in f)]
    files.sort(key=get_modified_time)

    for f in files:
        with open(f, "r") as rf:
            lines = rf.readlines()
            for l in lines:
                for sk in search_keys:
                    if sk in l:
                        return f"\t\tALERT: \033[48;5;1m\033[38;5;226mFound the pill '{sk}' in history file {f} \033[0m"
    
    return ""

def tester_trick_check(fullpath, vsc_hist_dir):
    search_keys = ["printf.*Temple Of Mota", "sparkling rainbow","Rainbow Poop", "Unicorn Toilet Room", "large, peculiar looking statue is standing in the middle of the square", "Austral Square, home of Kate's Diner, lies to your east", "potion cure critical critic","Ninja Sword of the Ninja","Gladiator Trident of the Arena","You bought.*Excalibur", "10.*Knight Sword of the Round Table","10.*Magic Staff of the Wizard","10.*potion cure critical critic","10.*Crystal Sword of the Mage","1.*Golden Axe of the Dwarf"]
    
    prohibited_line = 0
    with open(fullpath, "r") as rf:
        lines = rf.readlines()
        for l in lines:
            for sk in search_keys:
                if re.search(sk, l):
                    if not re.search(f"/.*{sk}", l):
                        prohibited_line += 1
    
    files = [os.path.join(vsc_hist_dir, f) for f in os.listdir(vsc_hist_dir) 
             if os.path.isfile(os.path.join(vsc_hist_dir, f)) and (f.endswith('.c') or f.endswith('.cpp')) and ("_" not in f)]
    files.sort(key=get_modified_time)

    prohibited_hist_line=0
    for f in files:
        print_count = 0        
        with open(f, "r") as rf:
            lines = rf.readlines()
            for l in lines:
                for sk in search_keys:
                    if re.search(sk, l):
                        prohibited_hist_line += 1
                if re.search("/flag", sk):
                    prohibited_hist_line += 9999999
                        
    if (prohibited_line + prohibited_hist_line) > 5:
        if prohibited_line > 0:
            return f"\t\tALERT: \033[48;5;1m\033[38;5;226mFound {prohibited_line} prohibited strings in main and {prohibited_hist_line} prohibited strings in history files\033[0m"
        else:
            return f"\t\tALERT: \033[48;5;1m\033[38;5;226mFound {prohibited_hist_line} prohibited strings in history files\033[0m"
    return ""


def analyze_comments(vsc_hist_dir, partial_output_path):
    # Function to get the modified time of a file
    

    # Function to extract comments from a file (assuming comments start with # for Python or // for C++/C)
    def extract_comments(file_path):
        comments = []
        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()
                if line.startswith('//'):  # You can modify this for other comment styles
                    if "//pc" in line or "{" in line or "}" in line or line.strip().endswith(";"):
                        pass 
                    else:
                        comments.append(line)
        return comments

    # Improved function to compare comments in both directions
    def compare_comments(prev_comments, curr_comments):
        # Create dictionaries with stripped versions of comments as keys and original comments as values
        prev_comments_dict = {comment.replace(" ", ""): comment for comment in prev_comments}
        curr_comments_dict = {comment.replace(" ", ""): comment for comment in curr_comments}

        # Convert dictionaries to sets for comparison, using keys (stripped versions)
        prev_comments_set = set(prev_comments_dict.keys())
        curr_comments_set = set(curr_comments_dict.keys())

        # Comments missing in current file but present in previous file
        disappeared_keys = prev_comments_set - curr_comments_set
        disappeared_comments = [prev_comments_dict[key] for key in disappeared_keys]

        # New comments added in current file but missing in previous file
        added_keys = curr_comments_set - prev_comments_set
        added_comments = [curr_comments_dict[key] for key in added_keys]

        return list(disappeared_comments), list(added_comments)


    # Get list of files sorted by last modified time
    comment_message = ""
    #files = [os.path.join(vsc_hist_dir, f) for f in os.listdir(vsc_hist_dir) if os.path.isfile(os.path.join(vsc_hist_dir, f))]
    files = [os.path.join(vsc_hist_dir, f) for f in os.listdir(vsc_hist_dir) 
             if os.path.isfile(os.path.join(vsc_hist_dir, f)) and (f.endswith('.c') or f.endswith('.cpp')) and ("_" not in f)]
    files.sort(key=get_modified_time)
    
    total_comments = {}
    full_output_filepath = f"{partial_output_path}{os.path.basename(vsc_hist_dir)}.cmts"
    # Prepare the output file
    with open(full_output_filepath, 'w') as output_file:
        output_file.write(f"Directory: {vsc_hist_dir}\n\n")
        
        diss_count = []
        add_count = []
        # Compare consecutive files
        for i in range(1, len(files)):
            prev_file = files[i - 1]
            curr_file = files[i]
            
            prev_comments = extract_comments(prev_file)
            curr_comments = extract_comments(curr_file)
            # print(f"{prev_file}\n {prev_comments}")
            # print(f"{curr_file}\n {curr_comments}")
            # Compare comments
            disappeared_comments, added_comments = compare_comments(prev_comments, curr_comments)
            

            if disappeared_comments or added_comments:
                # Write the file paths and comment differences to the output file
                               
                if disappeared_comments and len(disappeared_comments) > 4:
                    keystr = "".join(disappeared_comments)
                    total_comments[keystr] = total_comments.get(keystr,{"added": 0, "removed":0})
                    total_comments[keystr]["removed"] += 1
                    
                    diss_count.append(len(disappeared_comments))
                    output_file.write(f"Previous file: {prev_file}\n")
                    output_file.write(f"Current file: {curr_file}\n")
                    #print(f"{os.path.basename(prev_file)} vs {os.path.basename(curr_file)} with {len(disappeared_comments)} dissappeared comments")
                    output_file.write("Disappeared comments:\n")
                    for comment in disappeared_comments:
                        output_file.write(f"{comment}\n")
                    output_file.write("\n")

                if added_comments and len(added_comments) > 4:
                    keystr = "".join(added_comments)
                    total_comments[keystr] = total_comments.get(keystr,{"added": 0, "removed":0, "prev" : f"{os.path.basename(prev_file)}", "current": f"{os.path.basename(curr_file)}"})
                    total_comments[keystr]["added"] += 1
                    add_count.append(len(added_comments))
                    output_file.write(f"Previous file: {prev_file}\n")
                    output_file.write(f"Current file: {curr_file}\n")
                    #print(f"{os.path.basename(prev_file)} vs {os.path.basename(curr_file)} with {len(added_comments)} added comments")
                    output_file.write("Added comments:\n")
                    for comment in added_comments:
                        output_file.write(f"{comment}\n")
                    output_file.write("\n")
                
        diss_over_limit = [f"{x}R" for x in diss_count if x > 4]
        add_over_limit = [f"{x}A" for x in add_count if x > 4]
        if len(diss_over_limit) > 0 or len(add_over_limit) > 0:
            total_comment_changes = add_over_limit + diss_over_limit
            if len(total_comment_changes) > 4:
                comment_message += f"\t\tWARN: \033[38;5;11mFound suspicious number of comment changes {total_comment_changes} comments/{os.path.basename(full_output_filepath)} for details\033[0m"
            
            if len(total_comments) > 0: 
                for keystr, value in total_comments.items():
                    if value["added"] > 0 and value["removed"] > 0 :
                        display_keystr = keystr.replace("//","\n\t\t\t\t//")
                        display_keystr = display_keystr.replace("#","\n\t\t\t\t#")
                        display_keyarr = display_keystr.split("\n")
                        display_keystr = '; '.join([d.strip() for d in display_keyarr[1:9]])
                        
                        comment_message += f"\n\t\t\t Same comments added={value['added']} removed={value['removed']} : {display_keystr}"
            return comment_message
    return comment_message  
        
def file_recently_updated(file_path):
    
    # Check if the file exists
    if os.path.exists(file_path):
        # Get the current time and the file's last modification time
        current_time = time.time()  # Current time in seconds since the epoch
        file_mod_time = os.path.getmtime(file_path)  # Last modification time of the file
        
        # Check if the file was modified within the last 5 minutes (300 seconds)
        if current_time - file_mod_time < 300:
            return True  
        else:
            
            return False 
    else:
        return False


def get_bytes_entered_by_keyboard(vsc_history_dir):

    key_logger_fp = os.path.join(vsc_history_dir, "key.log")
    total_bytes = 0
    if os.path.exists(key_logger_fp):
        with open(key_logger_fp, "r") as rf:
            for line in rf.readlines():
                match = re.search(r'.*: (\d+)b .*', line)

                if match:
                    total_bytes += int(match.group(1))
    
    if total_bytes == 0:
        return "0b"
    if total_bytes > 1000:
        return f"{total_bytes/1000:.1f} kb \033[0m"    

    return f"\033[38;5;70m{total_bytes} bytes  \033[0m"


def analyze_first_file_size(abs_file_path, version_count, vsc_hist_dir, vsc_display_his_dir ):
    first_file_size_message = ""
    # originally we had max files kept set to 50, if this is hit then it rotates the files out
    if version_count == 50:
        return first_file_size_message
    # TODO: may want to add a time component to this instead of just looking at the first file in the history
    #       look at the file over the first few minutes, in case they are building by just copy and pasting one line    
    #       at a time to avoid detection

    # pig latin only check 
    if abs_file_path.endswith("04-c-pigl/01/main.c"):
        old_fn, old_size = get_oldest_c_cpp_file_size(vsc_hist_dir)        
        with open(old_fn, "r") as rf:
            lines = rf.readlines()
        found = False 
        for line in lines:
            if "CODE: ok, this is a bit scary, it's very empty in here. DON'T PANIC!" in line:
                found = True
                break 
        if (old_size > 500 and found) or (old_size > 300 and not found):
            display_fn = os.path.join(vsc_display_his_dir, os.path.basename(old_fn))
            first_file_size_message = f"\t\tWARN: \033[38;5;202mFirst file {display_fn} is unusually large at {old_size} bytes\033[0m"
            if not found:
                first_file_size_message += f" \033[38;5;202mCODE COMMENT NOT FOUND\033[0m"
    
    # mud check data.c
    if abs_file_path.endswith("05-mud/01/data.c"):
        old_fn, old_size = get_oldest_c_cpp_file_size(vsc_hist_dir)
        if old_size > 250:
            display_fn = os.path.join(vsc_display_his_dir, os.path.basename(old_fn))
            first_file_size_message = f"\t\tWARN: \033[38;5;202mFirst file {display_fn} is unusually large at {old_size} bytes\033[0m"   

    # mud check level 3, operations.c
    if abs_file_path.endswith("05-mud/03/operations.c") :
        old_fn, old_size = get_oldest_c_cpp_file_size(vsc_hist_dir)
        if old_size > 250:
            display_fn = os.path.join(vsc_display_his_dir, os.path.basename(old_fn))
            first_file_size_message = f"\t\tWARN: \033[38;5;202mFirst file {display_fn} is unusually large at {old_size} bytes\033[0m"   

     # mudshop shop.cpp check
    if abs_file_path.endswith("06-mudshop/02/shop.cpp") :
        old_fn, old_size = get_oldest_c_cpp_file_size(vsc_hist_dir)
        with open(old_fn, "r") as rf:
            lines = rf.read()
        if "pokemon_list" not in lines and "SongNode" not in lines and old_size > 250:
            display_fn = os.path.join(vsc_display_his_dir, os.path.basename(old_fn))
            first_file_size_message = f"\t\tWARN: \033[38;5;202mFirst file {display_fn} is unusually large at {old_size} bytes and does not contain pokemon_list from grouplab 9\033[0m"   

    return first_file_size_message

def run_analysis(pid, sid, analyze_files, show_all_diffs, save_tar):
    no_analysis =[]
    files_analzyed = [] 
    found_ai_results = False 
    vsc_analyze_info = {}

    for relative_file_path, absolute_file_path in analyze_files:
        files_analzyed.append(relative_file_path)
        vsc_analyze_info = analyze_vscode_history(relative_file_path, absolute_file_path, show_all_diffs)
        if vsc_analyze_info is not None:
            vsc_hist_dir = vsc_analyze_info.get("vsc_hist_dir", None)
            if len(pid) > 0:
                last_dir = os.path.basename(vsc_hist_dir)
                vsc_display_hist_dir = f"tars/{pid}_history/{last_dir}"
            else:
                vsc_display_hist_dir = vsc_hist_dir

            # if project 05 and level 01, file data.c and main.c should start at a small size
            
            vsc_analyze_info["first_file_size_message"] = analyze_first_file_size(absolute_file_path, vsc_analyze_info.get("version_count",0), vsc_hist_dir, vsc_display_hist_dir )
            
            vsc_analyze_info["comments_message"] = analyze_comments(vsc_hist_dir, f"{report_output_dir}/comments/{pid}_{sid}_")
            add_per_min, vsc_analyze_info["crazy_growth_count"] = crazy_growth_count(vsc_hist_dir)

            vsc_analyze_info["sig_changes_message"] = analyze_for_significant_changes(vsc_hist_dir, pid)
            analyze_line_changes(vsc_hist_dir)
            vsc_analyze_info["big_pastes"] = find_big_paste(vsc_hist_dir)
            vsc_analyze_info["pill_search"] = pill_search(absolute_file_path, vsc_hist_dir)
            vsc_analyze_info["tester_trick_check"] = tester_trick_check(absolute_file_path, vsc_hist_dir)
            vsc_analyze_info["level_diff"] = analyze_diff_first_history_and_last_level(vsc_hist_dir, absolute_file_path, pid)
            
            keyboard_bytes = get_bytes_entered_by_keyboard(vsc_hist_dir)            
            
            show_version_count_as_warning = False 
            if vsc_analyze_info.get("version_count",0) == 1:
                if (relative_file_path.endswith("03-c-chars/06/main.c") or
                    relative_file_path.endswith("04-c-pigl/01/main.c") or relative_file_path.endswith("04-c-pigl/02/main.c") or relative_file_path.endswith("04-c-pigl/03/main.c") or relative_file_path.endswith("04-c-pigl/04/main.c") or
                    relative_file_path.endswith("05-mud/01/data.c") or relative_file_path.endswith("05-mud/01/main.c") or
                    relative_file_path.endswith("05-mud/03/operations.c") or 
                    relative_file_path.endswith("06-mudshop/02/shop.cpp")
                ):
                    show_version_count_as_warning = True 
                    
            show_large_message_as_warning = False 
            if len(vsc_analyze_info.get("large_message","")) > 0 :
                if (relative_file_path.endswith("04-c-pigl/01/main.c") or
                    relative_file_path.endswith("05-mud/01/data.c") or relative_file_path.endswith("05-mud/01/main.c") or relative_file_path.endswith("05-mud/03/operations.c") or 
                    relative_file_path.endswith("06-mudshop/01/shop.cpp") or
                    relative_file_path.endswith("06-mudshop/02/shop.cpp")
                ):
                    show_large_message_as_warning = True 
                    
            #print(json.dumps(vsc_analyze_info,indent=2))
            if ( 
                show_large_message_as_warning or show_version_count_as_warning or add_per_min > 400 or len(vsc_analyze_info.get("first_file_size_message","")) > 0 or 
                len(vsc_analyze_info.get("comments_message","")) > 0 or len(vsc_analyze_info.get("sig_changes_message","")) > 0 or
                len(vsc_analyze_info.get("big_pastes","")) > 0 or len(vsc_analyze_info.get("pill_search","")) > 0 or len(vsc_analyze_info.get("tester_trick_check")) > 0 or len(vsc_analyze_info.get("level_diff")) > 0
            ):
                if not found_ai_results: 
                    #if student_info > "":
                        #print(student_info)
                        # tar -czf ~/tmp/${pid}_code.tar.gz --exclude="*.bin" --exclude="system_tests" --exclude="*.o" --exclude="grplab*" --exclude="labw" cse240; 
                        # cd /home/hacker/.local/share/code-server/User; tar -czf ~/tmp/${pid}_history.tar.gz History; fi )
                    if save_tar:
                        code_tar_file = f"/home/me/tmp/tars/{pid}_code.tar.gz"
                        if not file_recently_updated(code_tar_file):
                            try:
                                subprocess.run(["tar","-czf", code_tar_file,'--exclude=*.bin', '--exclude=core', '--exclude=vgcore*','--exclude=system_tests', '--exclude=*.o', '--exclude=grplab*', '--exclude=labw', '--transform', f"s/^cse240/{pid}_code_cse240/", 'cse240'], cwd="/home/hacker")
                                subprocess.run(["tar","-czf",f"/home/me/tmp/tars/{pid}_history.tar.gz", '--transform', f"s/^History/{pid}_history/",'History'], cwd="/home/hacker/.local/share/code-server/User")
                            except Exception as ex:
                                print(ex)

                print(f"\t{relative_file_path}: \033[38;5;12m{vsc_analyze_info.get('version_count',0)} versions\033[0m, {vsc_analyze_info.get('time_spent', 0):.2f}h  keyboarded: {keyboard_bytes} {vsc_analyze_info.get('largest_diff_info','')} @ {vsc_display_hist_dir}")

                found_ai_results = True 
                #print(f"\t{relative_file_path}: \033[38;5;12m{vsc_analyze_info.get('version_count',0)} versions\033[0m, {vsc_analyze_info.get('time_spent', 0):.2f} hours worked {vsc_analyze_info.get('largest_diff_info','')}")

                #print(f"\t\tVSCode History Dir: {vsc_hist_dir}")
                #print(f"{vsc_analyze_info.get('large_message','')=} {vsc_analyze_info.get('first_file_size_message','')=} {vsc_analyze_info.get('comments_message','')=} {vsc_analyze_info.get('sig_changes_message','')=}")
                if show_version_count_as_warning:
                    print("\t\tWARN: \033[38;5;202mOnly 1 version file found !!!!\033[0m")
                if show_large_message_as_warning:
                    print(vsc_analyze_info.get("large_message",""))
                                
                if len(vsc_analyze_info.get("first_file_size_message","")) > 0 :
                    print(vsc_analyze_info.get("first_file_size_message",""))
                
                if len(vsc_analyze_info["crazy_growth_count"]) > 0:
                    print(vsc_analyze_info["crazy_growth_count"])
                    
                if len(vsc_analyze_info.get("comments_message","")) > 0 :
                    print(vsc_analyze_info.get("comments_message",""))

                if len(vsc_analyze_info.get("sig_changes_message","")) > 0:  
                    print(vsc_analyze_info.get("sig_changes_message",""))   
                
                if len(vsc_analyze_info.get("big_pastes","")) > 0:  
                    print(vsc_analyze_info.get("big_pastes",""))   

                if len(vsc_analyze_info.get("pill_search","")) > 0:  
                    print(vsc_analyze_info.get("pill_search",""))   

                if len(vsc_analyze_info.get("tester_trick_check","")) > 0:  
                    print(vsc_analyze_info.get("tester_trick_check",""))   
                
                if len(vsc_analyze_info.get("level_diff","")) > 0:  
                    print(vsc_analyze_info.get("level_diff",""))   
            else:
                print(f"\t✔️{relative_file_path}: \033[38;5;12m{vsc_analyze_info.get('version_count',0)} versions\033[0m, {vsc_analyze_info.get('time_spent', 0):.2f}h  keyboarded: {keyboard_bytes} {vsc_analyze_info.get('largest_diff_info','')} @ {vsc_display_hist_dir}")
        else:
            #print(f"No VSCode History for {relative_file_path}")
            no_analysis.append(relative_file_path)
            pass

    if not found_ai_results:
        if len(files_analzyed) == 0 :
            print(f"\tno files found to analyze ")    
        else:
            dn = os.path.dirname(files_analzyed[0]).split("/")
            dn = "/".join(dn[-2:])
            if len(no_analysis) == len(files_analzyed):
                print(f"\t{dn} no history ")    
            else:          
                print(f"\t{dn} Ok")

def main(args, clevel_work_dir):
    global report_output_dir
    global basedir
    global coders_work_dir
    global student_info
    global pid
    global sid
    global vscode_history_dir
    global extension_log_file

    coders_work_dir = clevel_work_dir

    print(f"{coders_work_dir=}")
    vscode_history_dir = Path("/home/hacker/.local/share/code-server/User/History")
    extension_log_file = Path("/home/hacker/cse240/.vscode/cp.dat")
    report_output_dir = f"/home/me/tmp/"
    basedir = ""
    pid=""

    analyze_files = []

    if not os.path.exists("/home/hacker/cse240"):
        if args.basedir is None:
            print("error --basedir must be supplied when running locally")
            sys.exit(123)
        report_output_dir = args.basedir
        basedir = args.basedir

    os.makedirs(f"{report_output_dir}/", exist_ok=True)
    os.makedirs(f"{report_output_dir}/comments", exist_ok=True)
    os.makedirs(f"{report_output_dir}/diffs/", exist_ok=True)
    os.makedirs(f"{report_output_dir}/tars/", exist_ok=True)
    os.makedirs(f"{report_output_dir}/reports/", exist_ok=True)

    # If we are in pwn.college then do this stuff
    if os.path.exists("/home/hacker/cse240"):
        if not os.path.exists("/home/me"):
            try :
                level_config_file = os.path.join("/challenge",".config", "level.json")
                with open("/home/hacker/.local/share/ultima/inter.dat", "a+") as wf:
                    current_datetime = datetime.now()
                    iso_format_datetime = current_datetime.isoformat()
                    with open(level_config_file) as cf:
                        level_config=json.load(cf)
                    pname = os.path.basename(level_config.get('hwdir', ''))
                    level = level_config.get('hwdir', '')
                    wf.write(f"{iso_format_datetime}: {pname}-{level} : Checker Run \n")

            except Exception as ex:
                with open("/home/hacker/.local/share/ultima/err.dat", "a+") as wf:
                    wf.write(f"Error writing to inter from checker, {ex}")                

            print("Cannot run checker in this mode, please contact course staff.")
            sys.exit(99)
        level_json_config = "/challenge/.config/level.json"
        if os.path.exists(level_json_config):
            with open(level_json_config, "r") as rw:
                level_data = json.load(rw)
        pid = ""
        sid = ""
        student_info = ""
        
        if args.student_info:
            cleaned_string = re.sub(r'^\d+\.\s+', '', args.student_info)
            student_info = cleaned_string.split(",")
            pid = student_info[4]
            sid = student_info[0]
            #check_and_append_pid(pid)
            
            student_info = (f" " + f"{student_info[4]} {student_info[2].replace('_',' ')} {student_info[1]} {student_info[0]} ")
        elif args.pid:
            pid = args.pid
        #else:
            #pid = find_vsnum()
                
        deactivation_message = count_deactivations()
            
        if student_info > "":
            if len(deactivation_message) > 0:
                print(student_info + deactivation_message)
            else:
                print(student_info)
        # if not save_tar enabled then this is part of a single report run and should show the deactivation message for the project/level report. 
        elif not args.save_tar and len(deactivation_message) > 0:
            print(deactivation_message)

        if args.checkdir is None and coders_work_dir is not None:
            analyze_files = get_file_paths(coders_work_dir)        
        elif args.checkdir is not None:
            if os.path.exists(args.checkdir):
                analyze_files = get_file_paths(args.checkdir)
            else:
                print(f"\tThe Path {args.checkdir} does not exist")
                print("\t\tCommand: " + ' '.join(sys.argv))
                sys.exit(104)
        else:
            print("\targs.checkdir is None and coders_work_dir is None")
            print("\t\tCommand: " + ' '.join(sys.argv))
            sys.exit(105)
        
        run_analysis(pid, sid, analyze_files, args.all_diffs, args.save_tar)    

    else:
        pid = args.pid 
        sid = "XXXXXXXXXX"
        path = os.path.join(args.basedir, f"{pid}_code_cse240", args.checkdir)
        if os.path.exists(path):
            analyze_files = get_file_paths(path)
        else:
            print(f"\tThe Path {path} does not exist")
            print("\t\tCommand: " + ' '.join(sys.argv))
            sys.exit(104)
        vscode_history_dir = Path(f"{args.basedir}/{pid}_history")
        print(analyze_files)
        run_analysis(pid, sid, analyze_files, args.all_diffs, args.save_tar)    
        
# if __name__ == "__main__":
#     main()
            