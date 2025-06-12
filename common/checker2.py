#!/usr/bin/env python3
import os
import sys 
import json
from pathlib import Path
import difflib
from datetime import datetime, timedelta
import argparse 
import subprocess 

# Get the current EUID
current_euid = os.geteuid()

# Set the EUID to 1000 for hacker
new_euid = 1000
os.seteuid(new_euid)

# Directory paths
coders_work_dir = os.getenv('clevel_work_dir')
vscode_history_dir = Path("/home/hacker/.local/share/code-server/User/History")

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
                    subprocess.run(["icdiff",prev_file_path, version_file])
                    print("^"*80)
            
            previous_size = file_size
            prev_file_path = version_file 
       
        if dirname is None:
            dirname = os.path.dirname(version_file)
    
    large_count = len(large_changes)
    
    if not all_diffs:
        
        largest_diff_info = f" Largest diff: {largest_diff} bytes ({largest_diff_prec})"
        
        if large_count > 0:
            #print_out = [f"{chg[2]}b" if chg[2] > 500 else f"{chg[2]/chg[3]*100:.0f}% in {chg[4]:.0f}s" for chg in large_changes]
            print_out = [f"{chg[2]}b in {chg[4]:.0f}s" for chg in large_changes]

            large_message += f"\t\tWARN: \033[38;5;11m {large_count} diffs exceed threashold {print_out} \033[0m details at diffs/{pid}_{sid}_{os.path.basename(file_path)}.diff"
            
            output_file_path=f"/home/me/tmp/diffs/{pid}_{sid}_{os.path.basename(file_path)}.diff"
            
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
              f.startswith('cpN') or f.startswith('cpB') or f.startswith('cpNB'))]
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


def analyze_for_significant_changes(directory_path):
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
        #print(f"{(prev_file, curr_file, similarity_ratio)}")
        if similarity_ratio < .6:
            significant_change_count += 1
            big_change_files.append((prev_file, curr_file, similarity_ratio))

    if significant_change_count > 0:
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
            sig_change_message += f"\n\t\t\t{os.path.basename(f1)} ({f1_size/1000:.1f}k) v. {os.path.basename(f2)} ({f2_size/1000:.1f}k) ::> similarity={similarity_ratio:.3f} time diff={f2time-f1time:.0f}s size diff={size_difference}b ({percent_diff:.0f}%)"

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
    search_keys = ["Now with Even More MUD"]
    
    with open(fullpath, "r") as rf:
        lines = rf.readlines()
        for l in lines:
            for sk in search_keys:
                if sk in l:
                    return f"\t\tWARN: \033[38;5;202mFound the pill '{sk}' in the submitted file {fullpath} \033[0m"
    
    files = [os.path.join(vsc_hist_dir, f) for f in os.listdir(vsc_hist_dir) 
             if os.path.isfile(os.path.join(vsc_hist_dir, f)) and (f.endswith('.c') or f.endswith('.cpp')) and ("_" not in f)]
    files.sort(key=get_modified_time)

    for f in files:
        with open(f, "r") as rf:
            lines = rf.readlines()
            for l in lines:
                for sk in search_keys:
                    if sk in l:
                        return f"\t\tWARN: \033[38;5;202mFound the pill '{sk}' in history file {f} \033[0m"
    
    return ""


def analyze_comments(vsc_hist_dir, partial_output_path):
    # Function to get the modified time of a file
    

    # Function to extract comments from a file (assuming comments start with # for Python or // for C++/C)
    def extract_comments(file_path):
        comments = []
        with open(file_path, 'r') as file:
            for line in file:
                line = line.strip()
                if line.startswith('#') or line.startswith('//'):  # You can modify this for other comment styles
                    if "//pc" in line or "{" in line or "}" in line or line.strip().endswith(";"):
                        pass 
                    else:
                        comments.append(line)
        return comments

    # Improved function to compare comments in both directions
    def compare_comments(prev_comments, curr_comments):
        prev_comments_set = set(prev_comments)
        curr_comments_set = set(curr_comments)

        # Comments missing in current file but present in previous file
        disappeared_comments = prev_comments_set - curr_comments_set

        # New comments added in current file but missing in previous file
        added_comments = curr_comments_set - prev_comments_set

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
            comment_message += f"\t\tWARN: \033[38;5;11mFound suspicious number of comment changes {total_comment_changes} comments/{os.path.basename(full_output_filepath)} for details\033[0m"
            
            if len(total_comments) > 0: 
                for keystr, value in total_comments.items():
                    if value["added"] > 0 and value["removed"] > 0 :
                        display_keystr = keystr.replace("//","\n\t\t\t\t//")
                        display_keystr = display_keystr.replace("#","\n\t\t\t\t#")
                        display_keyarr = display_keystr.split("\n")
                        display_keystr = '\n'.join(display_keyarr[0:8])
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


if __name__ == "__main__":
    if not os.path.exists("/home/me"):
        print("Cannot run checker in this mode, please contact course staff.")
        sys.exit(99)

    parser = argparse.ArgumentParser(description='A simple argparse example with optional positional argument.')

    # Add a positional argument that is optional (with nargs='?', it allows zero or one argument)
    parser.add_argument('checkdir', nargs='?', default=None, help='An optional value (default: None)')
    parser.add_argument('--all_diffs', '--all-diffs', '--all','-a', action='store_true', default=False, help='An option to view all icdiffs')
    parser.add_argument('--student_info','-s', type=str, default=None, help='Add pwn.college id to report ')

    # Parse the arguments
    args = parser.parse_args()
    level_json_config = "/challenge/.config/level.json"
    if os.path.exists(level_json_config):
        with open(level_json_config, "r") as rw:
            level_data = json.load(rw)
    pid = ""
    sid = ""
    student_info = ""
    found_ai_results = False 
    if args.student_info:
        student_info = args.student_info.split(",")
        pid = student_info[4]
        sid = student_info[0]
        #check_and_append_pid(pid)
        student_info = (f"\t" + f"{student_info[4]} {student_info[2].replace('_',' ')} {student_info[1]} {student_info[0]} ")
    #else:
        #pid = find_vsnum()
    
    os.makedirs("/home/me/tmp/", exist_ok=True)
    os.makedirs("/home/me/tmp/comments", exist_ok=True)
    os.makedirs("/home/me/tmp/diffs/", exist_ok=True)
    os.makedirs("/home/me/tmp/tars/", exist_ok=True)
    os.makedirs("/home/me/tmp/reports/", exist_ok=True)
    
    vsc_analyze_info = {}
    analyze_files = []
    if args.checkdir is None and coders_work_dir is not None:
        analyze_files = get_file_paths(coders_work_dir)        
    elif os.path.exists(args.checkdir):
        analyze_files = get_file_paths(args.checkdir)
    elif not os.path.exists(args.checkdir):
        print(f"Error, the Path {args.checkdir} does not exist")
    
    files_analzyed = [] 
    no_analysis =[]

    for relative_file_path, absolute_file_path in analyze_files:
        files_analzyed.append(relative_file_path)
        vsc_analyze_info = analyze_vscode_history(relative_file_path, absolute_file_path, args.all_diffs)
        if vsc_analyze_info is not None:
            vsc_hist_dir = vsc_analyze_info.get("vsc_hist_dir", None)
            
            # if project 05 and level 01, file data.c and main.c should start at a small size
            if relative_file_path.endswith("05-mud/01/data.c") and vsc_analyze_info.get("version_count",0) != 50:
                old_fn, old_size = get_oldest_c_cpp_file_size(vsc_hist_dir)
                vsc_analyze_info["first_file_size"] = ""
                if old_size > 250:
                    vsc_analyze_info["first_file_size_message"] = f"\t\tWARN: \033[38;5;202mFirst file {old_fn} is unusually large at {old_size} bytes\033[0m"
            if relative_file_path.endswith("04-c-pigl/01/main.c") and vsc_analyze_info.get("version_count",0) != 50:
                old_fn, old_size = get_oldest_c_cpp_file_size(vsc_hist_dir)
                vsc_analyze_info["first_file_size"] = ""
                with open(old_fn, "r") as rf:
                    lines = rf.readlines()
                found = False 
                for line in lines:
                    if "CODE: ok, this is a bit scary, it's very empty in here. DON'T PANIC!" in line:
                        found = True
                        break 
                if (old_size > 500 and found) or (old_size > 300 and not found):
                    vsc_analyze_info["first_file_size_message"] = f"\t\tWARN: \033[38;5;202mFirst file {old_fn} is unusually large at {old_size} bytes\033[0m"
                    if not found:
                        vsc_analyze_info["first_file_size_message"] += f" \033[38;5;202mCODE COMMENT NOT FOUND\033[0m"
               

            vsc_analyze_info["comments_message"] = analyze_comments(vsc_hist_dir, f"/home/me/tmp/comments/{pid}_{sid}_")
            vsc_analyze_info["sig_changes_message"] = analyze_for_significant_changes(vsc_hist_dir)
            vsc_analyze_info["big_pastes"] = find_big_paste(vsc_hist_dir)
            vsc_analyze_info["pill_search"] = pill_search(absolute_file_path, vsc_hist_dir)
            print(f"\t{relative_file_path}: \033[38;5;12m{vsc_analyze_info.get('version_count',0)} versions\033[0m, {vsc_analyze_info.get('time_spent', 0):.2f}h  {vsc_analyze_info.get('largest_diff_info','')} @ {vsc_hist_dir}")
            if ( 
                len(vsc_analyze_info.get("large_message","")) > 0 or len(vsc_analyze_info.get("first_file_size_message","")) > 0 or 
                len(vsc_analyze_info.get("comments_message","")) > 0 or len(vsc_analyze_info.get("sig_changes_message","")) > 0 or vsc_analyze_info.get("version_count",0) == 1 or
                len(vsc_analyze_info["big_pastes"]) > 0 or len(vsc_analyze_info["pill_search"]) > 0
            ):                
                if not found_ai_results and student_info > "":
                    print(student_info)
                    # tar -czf ~/tmp/${pid}_code.tar.gz --exclude="*.bin" --exclude="system_tests" --exclude="*.o" --exclude="grplab*" --exclude="labw" cse240; 
                    # cd /home/hacker/.local/share/code-server/User; tar -czf ~/tmp/${pid}_history.tar.gz History; fi )
                    code_tar_file = f"/home/me/tmp/tars/{pid}_code.tar.gz"
                    if not file_recently_updated(code_tar_file):
                        try:
                            subprocess.run(["tar","-czf", code_tar_file,'--exclude="*.bin"', '--exclude="system_tests"', '--exclude="*.o"', '--exclude="grplab*"', '--exclude="labw"','cse240'], cwd="/home/hacker")
                            subprocess.run(["tar","-czf",f"/home/me/tmp/tars/{pid}_history.tar.gz", 'History'], cwd="/home/hacker/.local/share/code-server/User")
                        except Exception as ex:
                            print(ex)

                found_ai_results = True 
                #print(f"\t{relative_file_path}: \033[38;5;12m{vsc_analyze_info.get('version_count',0)} versions\033[0m, {vsc_analyze_info.get('time_spent', 0):.2f} hours worked {vsc_analyze_info.get('largest_diff_info','')}")

                #print(f"\t\tVSCode History Dir: {vsc_hist_dir}")
                #print(f"{vsc_analyze_info.get('large_message','')=} {vsc_analyze_info.get('first_file_size_message','')=} {vsc_analyze_info.get('comments_message','')=} {vsc_analyze_info.get('sig_changes_message','')=}")
                if vsc_analyze_info.get("version_count",0) == 1:
                    print("\t\tWARN: \033[38;5;202mOnly 1 version file found !!!!\033[0m")

                if len(vsc_analyze_info.get("large_message","")) > 0 :
                    print(vsc_analyze_info.get("large_message",""))
                
                if len(vsc_analyze_info.get("first_file_size_message","")) > 0 :
                    print(vsc_analyze_info.get("first_file_size_message",""))
                
                if len(vsc_analyze_info.get("comments_message","")) > 0 :
                    print(vsc_analyze_info.get("comments_message",""))

                if len(vsc_analyze_info.get("sig_changes_message","")) > 0:  
                    print(vsc_analyze_info.get("sig_changes_message",""))   
                
                if len(vsc_analyze_info.get("big_pastes","")) > 0:  
                    print(vsc_analyze_info.get("big_pastes",""))   

                if len(vsc_analyze_info.get("pill_search","")) > 0:  
                    print(vsc_analyze_info.get("pill_search",""))   

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
        
    
    
    

            