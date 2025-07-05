#!/usr/bin/env python3


# pylint: disable=line-too-long
# pylint: disable=unspecified-encoding
# pylint: disable=missing-function-docstring

from pathlib import Path
import argparse
import difflib
from datetime import datetime
import json
import os
import re
import random
import shutil
import subprocess
import sys
import time
import hashlib
import glob
import base64 
import filecmp
if os.path.exists("/challenge/bin"):
    sys.path.append("/challenge/bin")
    from tester_db import save_results, init_db, save_test_results
else:


    def save_results(*args, **kwargs):
        pass
    

    def init_db():
        pass
    
    def save_test_results(*args, **kwargs):
        pass

RED = '\033[31m'
BLUE = '\033[1;94m'
GREEN = '\033[32m'
YELLOW = '\033[1;33m'
ORANGE = '\033[38;5;208m'
DARK_GREY = '\033[1;30m'
RESET_COLOR = '\033[0m'


OUTPUT_FILE_LINE_LIMIT = 20



# SQLite database
BASE_HOME_DIR = "/home/hacker"
BASE_CSE240_DIR = f"{BASE_HOME_DIR}/cse240"
DATABASE = f'{BASE_CSE240_DIR}/.vscode/trdb.db'
CHALLENGE_DIR = "/challenge"
SYSTEM_TESTS_DIR = f"{CHALLENGE_DIR}/system_tests"
LEVEL_CONFIG_FP = os.path.join(CHALLENGE_DIR, ".config", "level.json")
ED_ENV = False

if not os.path.exists(BASE_HOME_DIR) and os.path.exists("/course"):
    BASE_HOME_DIR = "/home/"
    BASE_CSE240_DIR = f"{BASE_HOME_DIR}"
    DATABASE = None
    CHALLENGE_DIR = BASE_HOME_DIR
    SYSTEM_TESTS_DIR = f"{CHALLENGE_DIR}/system_tests"
    LEVEL_CONFIG_FP = os.path.join(CHALLENGE_DIR, ".config", "level.json")
    with open(LEVEL_CONFIG_FP, 'r') as f:
        labnum = json.load(f).get("labid", "")
        if labnum == "":
            labnum = json.load(f).get("hw", "")

    # script is having difficulty removing the .fuse file on ed lessons
    # the extra steps are an attempt to work around this issue and 
    # still perform the renewal of the stest files.
    if os.path.exists(SYSTEM_TESTS_DIR):
        for root, dirs, files in os.walk(SYSTEM_TESTS_DIR, topdown=False):
            for name in files + dirs:
                full_path = os.path.join(root, name)
                try:
                    if os.path.isfile(full_path) or os.path.islink(full_path):
                        os.remove(full_path)
                    elif os.path.isdir(full_path):
                        shutil.rmtree(full_path)
                except Exception as e:
                    print(f"Error deleting {full_path}: {e}")
        try:
            shutil.rmtree(SYSTEM_TESTS_DIR)
        except:
            pass
    
    if os.path.exists(SYSTEM_TESTS_DIR):
        if os.path.exists(f"/course/grouplab{labnum}/system_tests"):
            for item in os.listdir(f"/course/grouplab{labnum}/system_tests"):
                s = os.path.join(f"/course/grouplab{labnum}/system_tests", item)
                d = os.path.join(SYSTEM_TESTS_DIR, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)
    else:
        shutil.copytree(f"/course/grouplab{labnum}/system_tests", SYSTEM_TESTS_DIR)

    ED_ENV = True


def chown_recursive(path, uid, gid):
    for root, dirs, files in os.walk(path):
        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            try:
                shutil.chown(dir_path, uid, gid)
            except FileNotFoundError:
                pass
        for file_name in files:
            file_path = os.path.join(root, file_name)
            try:
                shutil.chown(file_path, uid, gid)
            except FileNotFoundError:
                pass


def calculate_md5(file_path):
    # Create an MD5 hash object
    md5 = hashlib.md5()

    # Open the file in binary mode
    with open(file_path, 'rb') as f:
        # Read the file in chunks
        while chunk := f.read(8192):
            md5.update(chunk)

    # Return the hexadecimal digest of the hash
    return md5.hexdigest()


def compile_program(source_dir, other_compile_args=[], alt_target_name=""):
    if len(other_compile_args) > 0:
        print(f"Other compile args: {other_compile_args}")
    if len(alt_target_name) > 0:
        print(f"Using alternate target name: {alt_target_name}")
    binary_name = "main.bin"
    if len(alt_target_name) > 0:
        binary_name = alt_target_name
    output_path = os.path.join(source_dir, binary_name)
    if os.path.exists(output_path):
        os.remove(output_path)
    start_time = time.time()
    makefile_path = os.path.join(source_dir, "Makefile")
    if os.path.exists(makefile_path):
        # Use make to compile if a Makefile is present
        clean_command = ["make", "-C", source_dir, "clean"]
        if os.path.exists(output_path):
            os.remove(output_path)
        try:
            result = subprocess.run(clean_command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"make clean failed with return code {e.returncode}\n{e.stdout}\n{e.stderr}")
            sys.exit(101)

        compile_command = ["make", "-j", "10", "-C", source_dir]
    else:
        # Find the source file
        source_file = None
        for file in os.listdir(source_dir):
            if file.endswith(".c") or file.endswith(".cpp"):
                source_file = file
                break

        if source_file is None:
            print("No C or C++ source file found in the provided directory.")
            return False

        # Compile the program
        source_path = os.path.join(source_dir, source_file)

        if source_file.endswith(".c"):
            compile_command = ["/usr/bin/gcc", source_path, "-O0", "-Wall", "-Werror", "-g", "-o", output_path]
        elif source_file.endswith(".cpp"):
            compile_command = ["/usr/bin/g++", source_path, "-O0", "-Wall", "-Werror","-g", "-o", output_path]
        
        if other_compile_args and len(other_compile_args) > 0:
            compile_command.extend(other_compile_args)
        print(f"Compile Command: {BLUE}{' '.join(compile_command)}{RESET_COLOR}")
    try:        
        subprocess.run(compile_command, check=True, capture_output=True, text=True)
        if not ED_ENV:
            chown_recursive(source_dir, 1000, 1000)
        print(f"Build: {GREEN}\u2714 PASS{RESET_COLOR} - {time.time() - start_time:.2f}s")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Compilation failed: {e.returncode}\n{e.stdout}\n{e.stderr}")
        print(f"Compile Command:    {BLUE}{' '.join(compile_command)} {RESET_COLOR}")
        sys.exit(102)


def normalize_whitespace_and_case(text, case_sensitive=False):
    if case_sensitive:
        return ' '.join(text.split())
    else:
        return ' '.join(text.split()).lower()


def run_icdiff(expected_file, actual_file, tmp_test_diff_results):

    with open(tmp_test_diff_results, 'w') as f:
        try:
            cmd = ["icdiff"]
            if os.environ.get("COLS", 0) == 0:
                cmd = cmd + ["--cols","100" ]
            cmd += ["--color-map", "subtract:yellow_bold,add:black_bold", "--label", "Expected Output", "--label","Actual Program Output"]
            cmd += [expected_file, actual_file]
            
            result = subprocess.run(cmd, text=True, capture_output=True)
            f.write(result.stdout)
            if result.stdout:
                output_lines = result.stdout.splitlines()
                if len(output_lines) > OUTPUT_FILE_LINE_LIMIT:
                    output = "\n".join(output_lines[:OUTPUT_FILE_LINE_LIMIT]) + f"\n{DARK_GREY}... truncated see the rest in {tmp_test_diff_results}{RESET_COLOR}"
                else:
                    output = "\n".join(output_lines)
                print(output)

        except FileNotFoundError:
            print("icdiff is not installed. Please contact support via discord")


def find_longest_match_all_subpatterns(pattern, input_string):
    longest_match = ""
    longest_pattern = ""
    pattern_length = len(pattern)

    for i in range(pattern_length):
        for j in range(i + 1, pattern_length + 1):
            sub_pattern = pattern[i:j]
            if len(sub_pattern) >= 5:  # Only consider sub-patterns of length 5 or more
                try:
                    match = re.search(sub_pattern, input_string)
                    if match and len(sub_pattern) > len(longest_pattern):
                        longest_pattern = sub_pattern
                        longest_match = match.group()
                except re.error:
                    pass

    return longest_pattern


def find_longest_match_start_to_end(pattern, input_string):
    longest_match = ""
    longest_pattern = ""
    pattern_length = len(pattern)

    for j in range(5, pattern_length + 1):  # Start from length 5
        sub_pattern = pattern[:j]
        try:
            match = re.search(sub_pattern, input_string)
            if match and len(sub_pattern) > len(longest_pattern):
                longest_pattern = sub_pattern
                longest_match = match.group()
        except re.error:
            pass

    return longest_pattern


def find_longest_regex_match(pattern, input_string, threshold=50):
    if len(pattern) > threshold:
        return find_longest_match_start_to_end(pattern, input_string)
    else:
        return find_longest_match_all_subpatterns(pattern, input_string)


def find_closest_match(expected_line, actual_lines, regex=False):
    # Function to apply blue color to matching text
    def highlight_match(text, start, end):
        if len(text) > (end + 4):
            return text[:start] + BLUE + text[start:end] + RED + text[end:end+2] + RESET_COLOR + text[end+2:]
        return text[:start] + BLUE + text[start:end] + RED + text[end:] + RESET_COLOR

    # Finding the closest match
    closest_index = -1
    highest_ratio = 0
    closest_match = None
    closest_match_start = 0
    closest_match_end = 0
    longest_sub_pattern_size = 3
    
    # Apartial match must match at least 40% of the expected line to qualify as a partial match
    MIN_MATCH_SIZE = round(len(expected_line) * .4, 0)

    for index, line in enumerate(actual_lines):
        if len(line) < 3:
            continue
        
        if regex:
            longest_expected_line_match = find_longest_regex_match(expected_line, line)
            try:
                match = re.search(longest_expected_line_match, line)
                if match and match.end() - match.start() > 3:
                    sub_pattern_size = len(longest_expected_line_match)
                    if sub_pattern_size > longest_sub_pattern_size:
                        longest_sub_pattern_size = sub_pattern_size
                        match_size = match.end() - match.start()
                        match_ratio = match_size / max(len(longest_expected_line_match), len(line))
                        if match_size > MIN_MATCH_SIZE and match_ratio > highest_ratio:
                            highest_ratio = match_ratio
                            closest_index = index
                            closest_match = line
                            closest_match_start = match.start()
                            closest_match_end = match.end()
            except re.error:
                print(f"Error with re.search on {longest_expected_line_match}")
        else:
            matcher = difflib.SequenceMatcher(None, expected_line, line)
            match = matcher.find_longest_match(0, len(expected_line), 0, len(line))
            if match.size > MIN_MATCH_SIZE and matcher.ratio() > highest_ratio:
                highest_ratio = matcher.ratio()
                closest_index = index
                closest_match = line
                closest_match_start = match.b
                closest_match_end = match.b + match.size

    if closest_index == -1:
        return None, None, None

    highlighted_match = highlight_match(closest_match, closest_match_start, closest_match_end)
    marker = " " * (closest_match_end-2) + "↑" * 5
    return closest_index, highlighted_match, marker


def match_file_output(expected_lines, actual_lines, output_type, case_sensitive):
    """Match expected lines to actual lines while allowing skips and ignoring case."""
    expected_lines = [normalize_whitespace_and_case(line, case_sensitive) for line in expected_lines]

    actual_lines = [normalize_whitespace_and_case(line, case_sensitive) for line in actual_lines]

    output_match_report = {"passed": False, "unexpected": [], "missing":[], "unexpectedToken": [], "matchesFound": 0 }

    # Check each unexpected line against all actual lines
    for expected_line in expected_lines:
        for actual_line in actual_lines:
            if output_type == "regex":
                if re.search(expected_line, actual_line):
                    output_match_report["matchesFound"] += 1
                    break
            else:
                if expected_line in actual_line:
                    output_match_report["matchesFound"] += 1
                    break
        else:
            output_match_report["missing"].append(expected_line)
            break


    output_match_report["passed"] = len(output_match_report["missing"]) == 0

    return output_match_report


def match_output(expected_lines, actual_lines, unexpected_output, output_type, case_sensitive=False):
    """Match expected lines to actual lines while allowing skips and ignoring case."""
    unexpected_lines = [normalize_whitespace_and_case(line, case_sensitive) for line in unexpected_output]
    expected_lines = [normalize_whitespace_and_case(line, case_sensitive) for line in expected_lines]
    actual_lines = [normalize_whitespace_and_case(line, case_sensitive) for line in actual_lines]

    output_match_report = {"passed": False, "unexpected": [], "missing":[], "unexpectedToken": [], "matchesFound": 0 }

    # Check each unexpected line against all actual lines
    for unexpected_line in unexpected_lines:
        for actual_line in actual_lines:
            if output_type == "regex":
                if re.search(unexpected_line, actual_line):
                    output_match_report["unexpectedToken"].append(unexpected_line)
                    output_match_report["unexpected"].append(actual_line)
                    return output_match_report
            else:
                if unexpected_line in actual_line:
                    output_match_report["unexpectedToken"].append(unexpected_line)
                    output_match_report["unexpected"].append(actual_line)
                    return output_match_report

    actual_iter = iter(actual_lines)

    # the unexpected line search goes through all actual lines once,
    # forcing each expected_line to come after the next line
    actual_index = 0
    for ex_line_index, expected_line in enumerate(expected_lines):
        # for actual_line in actual_iter:
        found = False
        last_actual_index = actual_index
        for x in range(actual_index, len(actual_lines)):
            actual_line = actual_lines[x]
            # print(f"#######    {expected_line}, {actual_line}, ")
            if output_type == "regex":
                if re.search(expected_line, actual_line):
                    output_match_report["matchesFound"] += 1
                    break
            else:
                if expected_line in actual_line:
                    output_match_report["matchesFound"] += 1
                    break
            actual_index += 1
        else: # if it completes (it does not find a match)
            output_match_report["missing"].append(expected_line)
            # did match occurr earlier in output?
            early_match_index = -1
            for x in range(last_actual_index-1, 0, -1):
                actual_line = actual_lines[x]
                if output_type == "regex":
                    if re.search(expected_line, actual_line):
                        early_match_index = x 
                        break
                else:
                    if expected_line in actual_line:
                        early_match_index = x 
                        break
            if early_match_index != -1:
                output_match_report["closestMatchIndex"] = early_match_index
                output_match_report["closestMatch"] = f"The expected output #{ex_line_index+1} \"{expected_line}\" is not being found after #{ex_line_index} \"{expected_lines[ex_line_index-1]}\". However, it is being found earlier in the output, which indicates the output is possibly printing the output in the wrong order. The output of the program should follow the order of the expected output (above)."
                output_match_report["closestMarker"] = " "
            else:
                
                closest_index, highlighted_text, marker = find_closest_match(expected_line, actual_lines, regex=(output_type=="regex"))

                if (closest_index is not None):
                    if last_actual_index > closest_index:
                        # if the partial match is being found before the prior expected line in the output, then we probably do not want to mention it, we will just claim it was not found.
                        pass
                    else:
                        output_match_report['closestMatchIndex'] = closest_index
                        output_match_report["closestMatch"] = highlighted_text
                        output_match_report["closestMarker"] = marker
                # else no partial match was found, so we will just tell them it was not found            
            
            # let's only find one missing thing
            break

    output_match_report["passed"] = len(output_match_report["unexpected"]) == 0 and len(output_match_report["missing"]) == 0

    return output_match_report


def is_on_path(filename):
    # Get the system's PATH environment variable
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)

    # Iterate through each directory in PATH
    for directory in path_dirs:
        # Construct the full path to the file
        file_path = os.path.join(directory, filename)
        # Check if the file exists and is executable
        if os.path.isfile(file_path) and os.access(file_path, os.X_OK):
            return True

    return False


def extract_numbers_for_sorting(filename):
    match = re.search(r'(\d+)\.(\d+)\.(\d+)', os.path.basename(filename))
    if match:
        major, middle, minor = match.groups()
        # Construct a tuple with integer parts to ensure proper comparison
        return (int(major)*100+int(middle), int(minor))
    else:
        match = re.search(r'(\d+)\.(\d+)', os.path.basename(filename))
        if match:
            major, minor = match.groups()
            # Construct a tuple with integer parts to ensure proper comparison
            return (int(major), int(minor))
        return (-1, -1)


def extract_numbers(filename):
    match = re.search(r'(\d+)\.(\d+)\.(\d+)', os.path.basename(filename))
    if match:
        major, middle, minor = match.groups()
        # Construct a tuple with integer parts to ensure proper comparison
        return (int(major), int(middle), int(minor))
    else:
        match = re.search(r'(\d+)\.(\d+)', os.path.basename(filename))
        if match:
            major, minor = match.groups()
            # Construct a tuple with integer parts to ensure proper comparison
            return (int(major), int(minor), 0)
        return (-1, -1, -1)


def file_output_failed_test_information(target_path, test, args, input_data, expected_output_list, test_name, test_description, check_file, actual_output_list, out_match_report, case_sensitive=False, start_time=None, hidden_test=False, output_type=""):
    tmp_test_outputdir = os.path.join("/tmp", "test_output")
    os.makedirs(tmp_test_outputdir, mode=0o755, exist_ok=True)

    failed_test_message(target_path, args, input_data, test_name, test_description, start_time, expected_output=expected_output_list, message=f"missing output in {check_file}", hidden_test=hidden_test, output_type=output_type)

    if out_match_report["matchesFound"] > 0:
        print(f"\tMatches found    : {GREEN}{out_match_report['matchesFound']} {RESET_COLOR}out of {len(expected_output_list)}")

    if len(out_match_report["missing"]) > 0:
        print(f"\tMissing from file: {ORANGE}" + ', '.join(out_match_report["missing"]) + RESET_COLOR)

    if not hidden_test or os.path.exists("/home/me"):
        expected_normalized = '\n'.join(normalize_whitespace_and_case(line, case_sensitive) for line in expected_output_list)
        preprocessed_expected_filename = os.path.join(tmp_test_outputdir, f"{test}_expected_in_{os.path.basename(check_file)}.output")
        with open(preprocessed_expected_filename, 'w') as f:
            f.write(expected_normalized)

        # Write actual output to a temporary file for icdiff comparison
    actual_normalized = '\n'.join(normalize_whitespace_and_case(line, case_sensitive) for line in actual_output_list)

    pattern = r"pwn.college\{.*?\}"
        # Use re.sub to replace the pattern with an empty string
    actual_normalized = re.sub(pattern, "", actual_normalized, flags=re.DOTALL)

    preprocessed_actual_filename = os.path.join(tmp_test_outputdir, f"{test}_actual_{os.path.basename(check_file)}.output")

    with open(preprocessed_actual_filename, 'w') as f:
        f.write(actual_normalized)

    print(f"--------<[ {test} Output for {os.path.basename(check_file)} located at {preprocessed_actual_filename} ]>--------")
    print(actual_normalized)
    print(f"{DARK_GREY}↑ EOF ↑{RESET_COLOR}")
    print(DARK_GREY + f"-"*80 + RESET_COLOR)
    


def output_failed_test_information(target_path, test, args, input_data, expected_output_list, test_name, test_description, actual_output_list, out_match_report, case_sensitive=False, start_time=None, hidden_test=False,output_type=""):
    tmp_test_outputdir = os.path.join("/tmp", "test_output")
    os.makedirs(tmp_test_outputdir, mode=0o755, exist_ok=True)

    failed_test_message(target_path, args, input_data, test_name, test_description, start_time, expected_output=expected_output_list, hidden_test=hidden_test,output_type=output_type, missing=out_match_report["missing"])

    if hidden_test and not os.path.exists("/home/me"):
        return

    closestMatchExist = False
    if out_match_report["matchesFound"] > 0:
        print(f"\tMatches found: {GREEN}{out_match_report['matchesFound']} {RESET_COLOR}out of {len(expected_output_list)}")

    if len(out_match_report["missing"]) > 0:
        if 'closestMatchIndex' in out_match_report:
            lineno = f"{out_match_report['closestMatchIndex']+1}"
            print(f"\tFailed to find in output {' ' * len(lineno)} : \"{YELLOW}" + ', '.join(out_match_report["missing"]) + '"' + RESET_COLOR)
            print(f"\tClosest match is at line {lineno} : {out_match_report['closestMatch']}")
            closestMatchExist = True
        else:
            print(f"\tFailed to find in output: {YELLOW}\"" + ', '.join(out_match_report["missing"]) + '"' + RESET_COLOR)
    
    # target_text_path = ' '.join([target_path])
    # target_text_path = target_text_path.replace("/challenge/system_tests/", "./")

    # print(f"\tRun simlar test: {target_text_path} {' '.join(args)} {RESET_COLOR}")
    
    if len(out_match_report["unexpected"]) > 0:
        print(f"\tShould not have found in output: {RED}" + ', '.join(out_match_report["unexpected"]) + RESET_COLOR)
        print(f"\tUnexpected output found using: {ORANGE}" + ', '.join(out_match_report["unexpectedToken"]) + RESET_COLOR)

    expected_normalized = '\n'.join(normalize_whitespace_and_case(line, case_sensitive) for line in expected_output_list)
    preprocessed_expected_filename = os.path.join(tmp_test_outputdir, f"{test}_expected_normalized.output")
    with open(preprocessed_expected_filename, 'w') as f:
        f.write(expected_normalized)

        # Write actual output to a temporary file for icdiff comparison
    actual_normalized = '\n'.join(normalize_whitespace_and_case(line, case_sensitive) for line in actual_output_list)

    pattern = r"pwn.college\{.*?\}"
        # Use re.sub to replace the pattern with an empty string
    actual_normalized = re.sub(pattern, "", actual_normalized, flags=re.DOTALL)

    preprocessed_actual_filename = os.path.join(tmp_test_outputdir, f"{test}_actual_normalized.output")

    with open(preprocessed_actual_filename, 'w') as f:
        f.write(actual_normalized)

    if closestMatchExist:
        print(f"--------<[ {test}   (marked output of {tmp_test_outputdir}/{test}_actual_normalized.output) ]>--------")
        closest_match_index = out_match_report["closestMatchIndex"]
        start = 0
        if closestMatchExist > OUTPUT_FILE_LINE_LIMIT:
            print(f"{DARK_GREY}...skipping (get the full output using `cat <filename>`)...{RESET_COLOR}")
            start = closestMatchExist - 10
        actual_normalized_list = [normalize_whitespace_and_case(line, case_sensitive) for line in actual_output_list]
        for index in range(start, closest_match_index+OUTPUT_FILE_LINE_LIMIT):
            if index >= len(actual_normalized_list):
                break
            if index == closest_match_index:
                print(f"{DARK_GREY}{index+1:<2}{RESET_COLOR} " + out_match_report["closestMatch"])
                print(f"   " + out_match_report["closestMarker"])
            else:
                print(f"{DARK_GREY}{index+1:<2}{RESET_COLOR} " + actual_normalized_list[index])
        else:
            print(f"{DARK_GREY}...skipping (get the full output using `cat <filename>`)...{RESET_COLOR}")
        print(f"{DARK_GREY}↑ EOF ↑{RESET_COLOR}")
        print(DARK_GREY + f"-"*80 + RESET_COLOR)
    elif len(out_match_report["unexpected"]) > 0:
        # Unexpected output found, let's grep the output file to show the user
        env_vars = os.environ.copy()          # Start with a copy of the current environment
        env_vars['GREP_COLORS'] = 'mt=01;33'  # Change grep color to bold yellow

        print(f"--------<[ {test} Unexpected token found in output ]>--------")
        if (len(actual_output_list) > OUTPUT_FILE_LINE_LIMIT):
            cmd=["grep","--color=always", "-n", "-A10", "-B10", "-P", f".*{out_match_report['unexpectedToken'][0]}.*", preprocessed_actual_filename]            
            skipped_lable = f"{DARK_GREY}Actual Output File   : ...skipped lines, get the full output using: cat {preprocessed_actual_filename}{RESET_COLOR}"
        else:
            cmd=["grep","--color=auto", "-n", "-P", f".*{out_match_report['unexpectedToken'][0]}+.*" + "|(?=.)", preprocessed_actual_filename]
            
        result = subprocess.run(cmd, env=env_vars, capture_output=True, text=True)
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
        print(f"{DARK_GREY}↑ EOF ↑{RESET_COLOR}")
        print(DARK_GREY + f"-"*80 + RESET_COLOR)
        if len(skipped_lable) > 0:
            print(f"{skipped_lable}")
        else:
            print(f"{DARK_GREY}Actual Output File   : {preprocessed_actual_filename}{RESET_COLOR}")
    else:
        print(f"--------<[ {test} Difference between Expected Output and Actual Program Output ]>--------")
        tmp_test_diff_results = os.path.join(tmp_test_outputdir, f"{test}.diff")
        run_icdiff(preprocessed_expected_filename, preprocessed_actual_filename, tmp_test_diff_results)

        print(f"{DARK_GREY}↑ EOF ↑{RESET_COLOR}")
        print(DARK_GREY + f"-"*80 + RESET_COLOR)
        print(f"{DARK_GREY}Expected Output File : {preprocessed_expected_filename}")
        print(f"Actual Output File   : {preprocessed_actual_filename}")
        print(f"Diff Results File    : {tmp_test_diff_results}{RESET_COLOR}")

    print("")


def failed_test_message(target_path, args, input_data, test_name, test_description, start_time=None, expected_output=None, message="", hidden_test=False, output_type="", missing=[]):
    print(f"{RED}FAIL{RESET_COLOR} {test_name} {message}")
    formmated_args = []

    for param in args:
        if target_path.endswith("gdb") and param == "-batch":
            continue
        if target_path.endswith("gdb") and param == "quit":
            param = "list"
        

        if ' ' in param:
            # Surround parameters with spaces in single quotes
            formmated_args.append(f"'{param}'")
        else:
            formmated_args.append(param)

    print(f"\tTest Desc        : {test_description}")
    # Check if os.path.basename(target_path) is found on the command path
    if is_on_path(os.path.basename(target_path)):
        local_path = os.path.basename(target_path)
    else:
        local_path = f"./{os.path.basename(target_path)}"
    #local_path = f"/challenge/bin/{os.path.basename(target_path)}"


    if hidden_test and not os.path.exists("/home/me"):
        print("\tProgram Input    : HIDDEN")
    else:
        if target_path.endswith("gdb"):
            print(f"\tManually Input (follow each command with a newline)   : {input_data.replace("\n"," ")}")    
            print(f"\tRun Test yourself:{BLUE} {' '.join([local_path])} {' '.join(formmated_args)}{RESET_COLOR}") 
        else:
            print(f"\tProgram Input    : {repr(input_data)}")
            if output_type == "regex":
                if len(expected_output) > 0:
                    print(f"\tRun Test yourself:{BLUE} printf {repr(input_data)} | {' '.join([local_path])} {' '.join(formmated_args)} {RESET_COLOR}\n\t\tLook for the missing output.")
            else:
                print(f"\tRun Test yourself:{BLUE} printf {repr(input_data)} | {' '.join([local_path])} {' '.join(formmated_args)}{RESET_COLOR}")
        print("\t                   If getting a segmentation fault try removing or simplyfying the 'printf ...' statement.")    
        print("\t                   When you run the command above, the output needs to include the expected output below.")
        print("\t                   Remember that `.*` is a wildcard that matches any character zero or more times and `\\s*` matches any space zero or more times.")

    if expected_output is not None:
        if hidden_test and not os.path.exists("/home/me"):
            print(f"\tExpected Output  : HIDDEN")
            # print(f"\tExpected Output  : {expected_output}")
        else:

            if len(missing) > 0:
                new_out = []
                first_match_index = -1
                match_index = -1
                mark_pre = False
                mark_post = False
                # highlight the missing expected output in RED
                for m in missing:
                    for ex_index, ex in enumerate(expected_output):
                        ex = f'"{ex}"'
                        higlighted_string = highlight_keyword(ex, m)
                        new_out.append(higlighted_string)
                        if ex.lower().find(m.lower()) > -1:
                            if first_match_index == -1:
                                first_match_index = ex_index
                            match_index = ex_index
                starting_point = max(0, first_match_index - 5)
                ending_point = min(len(expected_output), match_index + 5)
                # mark up to 5 predecessing and 5 succeeding output values in DARK_GREY
                for i in range(starting_point, first_match_index):
                    new_out[i] = f"{DARK_GREY}{new_out[i]}{RESET_COLOR}"
                    mark_pre = True
                for i in range(match_index+1, ending_point):
                    new_out[i] = f"{DARK_GREY}{new_out[i]}{RESET_COLOR}"
                    mark_post = True
                #print(f"{first_match_index=}, {match_index=}, {starting_point=}, {ending_point=}")
                print(f"\tExpected Output  : [ ", end="")
                if mark_pre:
                    print(f"{DARK_GREY}...{RESET_COLOR}", end="")
                # if we don't convert to string, it will not print the color                
                print(', '.join(new_out[starting_point:ending_point]), end="")
                if mark_post:
                    print(f"{DARK_GREY}...{RESET_COLOR}", end="")
                print(" ]")
            else:
                print(f"\tExpected Output  : All expected output was found in the program output")

    if start_time is not None:
        print(f"\tTest ran in      : {time.time()-start_time:.2f}s")

def highlight_keyword(text, keyword):
    idx = text.lower().find(keyword.lower())
    if idx == -1:
        return text
    end = idx + len(keyword)
    return text[:idx] + YELLOW + text[idx:end] + RESET_COLOR + text[end:]

def pick_random_word(file_path):
    try:
        with open(file_path, 'r') as file:
            words = file.read().splitlines()
            if not words:
                return "No words found in the file."
            rando =  random.choice(words)
            if "\n" not in rando:
                rando = rando + "\n"
            return rando
    except FileNotFoundError:
        return ""


def demote():
    """
    Change the user ID and group ID of the process.
    """
    user_uid = 1000  # UID for the user
    user_gid = 1000  # GID for the user
    os.setgid(user_gid)
    os.setuid(user_uid)


def check_if_direct_flag_access(command_args, cwd, input_data, env):
    # Include strace in the command with the specific tracing options
    strace_cmd = ["strace", "-e", "trace=openat,read", "-f"] + command_args

    try:
        # Run the command with strace under the given conditions
        process = subprocess.run(
            command_args,
            cwd=cwd,
            input=input_data if isinstance(input_data, bytes) else input_data.encode('utf-8'),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        # Check stderr for attempts to read /flag
        if "/flag" in process.stderr:
            return True
        return False

    except subprocess.CalledProcessError as e:
        print(f"Error during command execution: {e}")
        return False


def run_target_program(test, working_directory, target_path, args, input_data, model_program=False, environmentVar={}, return_code=0, expected_output=None, hidden_test=False):
    result = None
    try:

        timeout_command = ['timeout', '-k','2', '10']
        command = timeout_command + [target_path] + args
        # print("[run_target_program] " +" ".join(command))
        # print(f"[run_target_program]  {source_dir}")
        # print(f"[run_target_program] {input_data}")
        # print(f"[run_target_program] {environmentVar=}")
        environmentVar.update(os.environ)
        do_check = return_code == 0

        if hidden_test:
            print("Executing hidden test")
            # if check_if_direct_flag_access([target_path] + args, cwd=working_directory, input_data=input_data, env=environmentVar):
            #     print("Error direct access of /flag detected in program, this is not permitted, please remove the code opening /flag")
            #     with open("/home/hacker/.local/share/ultima/error.log", "a+") as wf:
            #         current_datetime = datetime.now()
            #         # Convert to ISO 8601 format
            #         iso_format_datetime = current_datetime.isoformat()
            #         wf.write(f"{iso_format_datetime} Error direct access of /flag detected in program, this is not permitted, please remove the code opening /flag\n")

            result = subprocess.run(command, cwd=working_directory, input=input_data, text=True, encoding='latin-1',
                                capture_output=True, timeout=3, check=do_check, env=environmentVar)
        else:
            if ED_ENV:
                result = subprocess.run(command, cwd=working_directory, input=input_data, text=True, encoding='latin-1',
                                    capture_output=True, timeout=3, check=do_check, env=environmentVar)
            else:
                result = subprocess.run(command, cwd=working_directory, input=input_data, text=True, encoding='latin-1',
                                    capture_output=True, timeout=3, check=do_check, env=environmentVar, preexec_fn=demote)
        if result.returncode == 124:
            raise subprocess.TimeoutExpired("timeout caught it", 10)
        if not do_check:
            result.returncode == return_code

    except subprocess.TimeoutExpired as e:
        print(f"The execution ran for too long for {os.path.basename(target_path)}")
        if model_program:
            print("The execution of modelGood.bin took too long ")
            print("Try again if it occurrs again, please contact support via Discord")
        else:
            print("Usually, a timeout indicates a problem with the program failing to exit on receipt of an exit command. ")
            print(f"Verify that your program is exiting correctly and that the test case '{test}' is entering the exit command")
            print("Another issue that can cause this behavior is when the program fails to clear the buffer (check user inputs)")
            formmated_args = []
            for param in args:
                if target_path.endswith("gdb") and param == "-batch":
                    continue
                if target_path.endswith("gdb") and param == "quit":
                    param = "list"

                if ' ' in param:
                    # Surround parameters with spaces in single quotes
                    formmated_args.append(f"'{param}'")
                else:
                    formmated_args.append(param)
            print(f"\tCommand          :{BLUE} {' '.join([target_path])} {' '.join(formmated_args)}{RESET_COLOR}")
            print(f"\tInput Data:      :{repr(input_data)}")

            if result is not None:
                print("\tStandard Output:")
                print(result.stdout[:5000])
                print("\tStandard Error:")
                print(result.stderr[:5000])
            else :
                if ( e.stdout is not None and len(e.stdout) > 0):
                    print("\tStandard Output:")
                    print(e.stdout[:5000])
                if (e.stderr is not None and len(e.stderr) > 0):
                    print("\tStandard Error:")
                    print(e.stderr[:5000])
        sys.exit(104)
    except subprocess.CalledProcessError as cpe:
        print(f"\n{test}: {YELLOW} ERROR {os.path.basename(target_path)} {RESET_COLOR}")
        formmated_args = []
        for param in args:
            if target_path.endswith("gdb") and param == "-batch":
                    continue
            if target_path.endswith("gdb") and param == "quit":
                param = "list"

            if ' ' in param or len(param) == 0:
                # Surround parameters with spaces in single quotes
                formmated_args.append(f"'{param}'")
            else:
                formmated_args.append(param)

        print(f"\tCommand          :{BLUE} {' '.join([target_path])} {' '.join(formmated_args)}{RESET_COLOR}")
        print(f"\tCommand returned non-zero exit status of {cpe.returncode}")
        print(f"\tProgram Input    : {repr(input_data)}")

        if expected_output is not None:
            if hidden_test:
                print(f"\tExpected Output  : HIDDEN")
            else:
                print(f"\tExpected Output  : {expected_output}")

        if "SIGSEGV" in f"{cpe}" :
            print(f"\tError: {RED}Segmentation fault {RESET_COLOR} ")
            print("\tError Description: A segmentation fault, often abbreviated as \"segfault\" or \"SIGSEGV\" is an error that occurs when a program attempts to access memory that it shouldn’t. This can happen for several reasons, such as trying to read or write to a memory location that the operating system has not assigned to the program, or trying to write to a read-only location. The error is named because it usually means that the program tried to access a segment of memory that it has no permissions for, leading the operating system to terminate the program abruptly to protect itself and other running processes.")
            print(f"\tNext Step: try using valgrind to identify file and line number where the segfault occurred, {GREEN}\n\t\tvalgrind {' '.join([target_path])} {' '.join(formmated_args)}    {RESET_COLOR}")
        elif "stack smashing" in f"{cpe}"  :
            print(f"\tError: {RED}Stack Smashing{RESET_COLOR} ")
            print("\tError Description: A stack smashing error, commonly called a buffer overflow, occurs when a program writes more data to a buffer located on the stack than what is actually allocated for that buffer. This excess data can overwrite adjacent memory on the stack, including function return addresses, other data, and control information. Such an error often leads to corrupting the execution flow of the program, which can cause it to crash or behave unpredictably. ")
            print("\tNext Step: Run the program in the debugger to identify the location of the error. Notice the stack trace on the right hand side, click on each location, to see the location and identify the offending function.")
        else:
            print(f"\tError: {cpe}")

        if (len(cpe.stdout) > 0):
            print("\tStandard Output:")
            print(cpe.stdout)
        if (len(cpe.stderr) > 0):
            print("\tStandard Error:")
            print(cpe.stderr)
        if (model_program):
            print("\nTry again if it occurrs again, please contact support via Discord")

        sys.exit(121)

    except Exception as ex:

        print(f"\n{test}: {YELLOW}Execution ERROR while running {os.path.basename(target_path)} {ex} {RESET_COLOR}")
        import traceback
        traceback.print_exc()

        if (model_program):
            print("\nTry again if it occurrs again, please contact support via Discord")

        sys.exit(121)

    actual_output = result.stdout
    if (len(result.stderr) > 0):
        actual_output = result.stdout + "-"*100 + "\n" + result.stderr

    return actual_output


def nonprintable_test(target_path, args, input_data, test_name, test_description, actual_output, start_time, output_type=""):
    non_printable_regex = re.compile(r'[^\x20-\x7E\n\t\r]')
    if non_printable_regex.findall(actual_output):
        failed_test_message(target_path, args, input_data, test_name, test_description, start_time=start_time, output_type=output_type)

        print(f"Output contains non-printable characters. This is usually caused by using a c-string that's not terminated with a NULL ")
        print("or using a single character char as a string in a string function. See recent Lab where we created a function for ")
        print("printing non-printable characters in C, use the function to see where the non-printable characters are introduced.")
        print("The output below shows where the non-printable characters are appearing.")
        print("------- [ Marked Output ] -------")

        def replacer(match):
            char = match.group(0)
            return f'\033[31m\\x{ord(char):02X}\033[0m'
        marked_output = non_printable_regex.sub(replacer, actual_output)
        print(f"{marked_output}")
        print("")
        return False
    return True


def run_reset_commands(reset_commands):

    for cmd in reset_commands:
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed reset command {cmd} with return code {e.returncode}\n{e.stdout}\n{e.stderr}")
            sys.exit(102)


# Get the list of test files and sort them numerically
def run_test(source_dir, test_dir, test_json_file, target_path=None, expect_failure=False, case_sensitive=False, hidden_test=False):

    test = os.path.splitext(os.path.basename(test_json_file))[0]
    working_dir = source_dir
    try:
        with open(test_json_file, "r") as tjf:
            test_json = json.load(tjf)
    except json.decoder.JSONDecodeError as jde:
        print(f"An error was encountered reading the test case {test_json_file}")
        print(jde)
        sys.exit(27)

    reset_commands = test_json.get("resetCommands",[])

    if len(reset_commands) > 0:
        run_reset_commands(reset_commands)

    other_compile_args = test_json.get("otherCompileArgs", [])    
    alt_target_name = test_json.get("altTargetName", "altmain.bin")
    if len(other_compile_args) > 0:
        compile_program(source_dir, other_compile_args=other_compile_args, alt_target_name=alt_target_name)
        source_alt_main_bin = os.path.join(source_dir, alt_target_name)
        system_alt_test_main_bin = os.path.join(SYSTEM_TESTS_DIR, alt_target_name)
        if (os.path.exists(source_alt_main_bin)):
            kill_process(system_alt_test_main_bin)
            kill_process(source_alt_main_bin)
            shutil.copy(source_alt_main_bin, system_alt_test_main_bin)

    if target_path is None:
        target_filename = test_json.get("target", "main.bin")
        source_binary_path = os.path.join(working_dir, target_filename)
        # this exception is because test cases using gdb receive ./main.bin (I'm not sure this is still needed)
        if working_dir == "/challenge/model" and (test_json.get("type", "normal") == "gdb"):
            # copying the debug version of model/main.bin to system_tests

            working_dir = test_dir


        elif working_dir == "/challenge/model" and (test_json.get("type", "normal") == "valgrind"):
            # in this case let's copy /challenge/modelGood.bin if exists to /challenge/system_tests, so that we can run the valgrind tests from /challenge/system_tests
            working_dir = test_dir
            temp_bin_check = os.path.join(working_dir, "main.bin")

        else:
            working_dir = test_dir

        if not os.path.exists(source_binary_path):
            # this little addition was because root did not have the nix path in its path thus
            # when executing as root which was finding the wrong gdb
            if (os.path.exists(f"/nix/var/nix/profiles/default/bin/{target_filename}")):
                exec_path = f"/nix/var/nix/profiles/default/bin/{target_filename}"
            else:
                exec_path = shutil.which(target_filename)
            if exec_path:
                target_path = exec_path
        else:
            test_binary_path = os.path.join(test_dir, target_filename)

            target_path = test_binary_path

    # print(f"{target_path=}")
    test_type = test_json.get("type", "output_search")

    create_files = test_json.get("createFiles",[])
    if len(create_files) > 0:
        for finfo in create_files:
            filepath = finfo["filepath"]
            if "<testsdir>" in filepath:
                filepath = filepath.replace("<testsdir>", test_dir + "/")
            else:
                filepath = os.path.join(test_dir, filepath)
            with open(filepath, "w") as wf:
                wf.write(finfo["filedata"])
            os.chmod(filepath, 0o666)
            tmp_test_outputdir = os.path.join("/tmp", "test_output")
            os.makedirs(tmp_test_outputdir, mode=0o755, exist_ok=True)
            test_file = os.path.join(tmp_test_outputdir, f"{test}_data_{os.path.basename(filepath)}")
            shutil.copy(filepath, test_file)

    args = [a.replace("<testsdir>", test_dir + "/").replace("<sourcedir>", source_dir + "/")
            for a in test_json.get("args",[])]

    input_data = test_json.get("input", "")

    if isinstance(input_data, list):
        input_data = '\n'.join(input_data)
    input_data += "\n"

    if test_json.get("type", "") == "model_good_compare":
        random_input = test_json.get("random_input", "")
        if len(random_input) > 0 and os.path.exists(random_input):
            input_data = pick_random_word(random_input)

        expected_output = run_target_program(test, "/challenge/", "/challenge/modelGood.bin", args, input_data, model_program=True, hidden_test=hidden_test)
        expected_output_list = [line for line in expected_output.splitlines() if len(line) > 1]
    else:
        expected_output_list = test_json.get("output", [])

    expected_output_list = [string for string in expected_output_list if string.strip()]

    if "/challenge/" in test_json_file:
        print(f"System {test}: ", end="")
        if len(expected_output_list) == 0 and test_type == "output_search":
           raise ImportError("Test case is misconfigured, it is missing expected output")
    else:
        print(f"User {test}: ", end="")
        if len(expected_output_list) == 0 and test_type == "output_search":
            print(f"{RED}FAIL{RESET_COLOR} because no output has been defined for user test yet.")
            return False

    return_code = test_json.get("returnCode", 0)
    start_time = time.time()
    actual_output = run_target_program( test, working_dir, target_path, args, input_data, environmentVar=test_json.get("testEnvironmentVars",{}),
                                       return_code=return_code, expected_output=expected_output_list, hidden_test=hidden_test)

    test_name = test_json.get('name', '')
    test_description = test_json.get('description', '')

    if len(test_name) == 0:
        if expect_failure:
            test_name = test_json.get('nameOfModelBadTest', '')
            test_description = test_json.get('descriptionOfModelBadTest', '')
        else:
            test_name = test_json.get('nameOfModelGoodTest', '')
            test_description = test_json.get('descriptionOfModelGoodTest', '')
    if len(test_name) > 1:
        test_name = f" - {test_name}"

    test_name = test_name.replace("<testfilename>", os.path.basename(target_path))
    test_description = test_description.replace("<testfilename>", os.path.basename(target_path))

    if not test_json.get("allow_nonprintable_chars", True) and not nonprintable_test(target_path, args, input_data, test_name, test_description, actual_output, start_time=start_time):
       return False

    if test_type == "output_size":
        if len(actual_output) < test_json["max_size"]:
            print(f"{GREEN}\u2714 PASS{RESET_COLOR} {test_name} ran in {time.time()-start_time:.2f}s")
            return True
        else:
            failed_test_message(target_path, args, input_data, test_name, test_description, start_time, hidden_test=hidden_test, output_type="")
            print(f"Output was too large {len(actual_output)}b, the maximum allowed is {test_json['max_size']}b. Please remove extra prints and resubmit.")
            return False
    else:
        actual_output_list = actual_output.splitlines()
        check_file = test_json.get("checkFile", {})
        output_type = test_json.get("output_type", "")
        check_filepath = check_file.get("filepath", "")

        if check_filepath != "":
            check_filepath = check_filepath.replace("<testsdir>", test_dir + "/")
            with open(check_filepath, "r") as rf:
                actual_lines_in_file_list = rf.read().splitlines()

            expected_file_out_list = check_file.get("output",[])
            file_out_report = match_file_output(expected_file_out_list, actual_lines_in_file_list, output_type, case_sensitive)

            # if failed test then print error and exit
            if (not file_out_report["passed"]):
                file_output_failed_test_information(target_path, test, args, input_data, expected_file_out_list, test_name, test_description, check_filepath, actual_lines_in_file_list, file_out_report, case_sensitive=case_sensitive, start_time=start_time, hidden_test=hidden_test,output_type=output_type)
                return False

        out_match_report = match_output(expected_output_list, actual_output_list,  test_json.get("unexpectedOutput",[]), output_type, case_sensitive=case_sensitive)

        if (out_match_report["passed"] and expect_failure == False) or (not out_match_report["passed"] and expect_failure==True):
            print(f"{GREEN}\u2714 PASS{RESET_COLOR} {test_name} ran in {time.time()-start_time:.2f}s")
            if test_json.get("print_output", False):
                print(f"Output for {test}")
                print(actual_output);
            return True
        else:
            output_failed_test_information(target_path, test, args, input_data, expected_output_list, test_name, test_description, actual_output_list, out_match_report, case_sensitive=case_sensitive, start_time=start_time, hidden_test=hidden_test,output_type=output_type)
            return False
    return False

#
def verify_user_tests_unique(user_test_paths, test_dir):

    if test_dir is None or not os.path.exists(test_dir):
        return True

    test_cases = sorted(
        [os.path.join(test_dir, file) for file in os.listdir(test_dir) if file.startswith("stest") and file.endswith(".json")],
        key=extract_numbers_for_sorting
    )

    for ut_path in user_test_paths:
        with open(ut_path, "r") as rj:
            ut_json = json.load(rj)
        for test_json_file in test_cases:
            with open(test_json_file, "r") as rj:
                systest_json = json.load(rj)
            for user_arg in ut_json.get("args",[]):
                if len(user_arg) < 4:
                    continue
                for sys_arg in systest_json.get("args",[]):
                    user_arg = normalize_whitespace_and_case(user_arg.strip())
                    sys_arg = normalize_whitespace_and_case(sys_arg.strip())
                    if (user_arg == sys_arg):
                        print(f"Error: Argument in {os.path.basename(ut_path)} matches a system test argument, please use different argument values")
                        return False
                    if os.path.exists(user_arg) and os.path.exists(sys_arg):
                        user_arg = os.path.realpath(user_arg)
                        user_arg = os.path.normpath(user_arg)
                        sys_arg = os.path.realpath(sys_arg)
                        sys_arg = os.path.normpath(sys_arg)
                        if (user_arg == sys_arg):
                            print(f"Error: Argument in {os.path.basename(ut_path)} matches a system test argument, you cannot use the system test files for testing, please create your own files.")
                            return False
                        if filecmp.cmp(user_arg, sys_arg, shallow=False):
                            print(f"Error: the contents of a file path used in {os.path.basename(ut_path)} matches a system test file. The files {user_arg} and {sys_arg} are identical. Please use different files for testing.")
                            return False
                    
            for user_input in ut_json.get("input",[]):
                if len(user_input) < 4:
                    continue
                for sys_input in systest_json.get("input",[]):
                    user_input = normalize_whitespace_and_case(user_input.strip())
                    sys_input = normalize_whitespace_and_case(sys_input.strip())
                    if (user_input == sys_input):
                        print(f"Error: Input in {os.path.basename(ut_path)} matches a system test with the same input, please use different values for this test's input values")
                        return False
                    
    return True


def clean_up(target_dir):
    if target_dir == "/challenge/model":
        return
    main_file = os.path.join(target_dir, "main.bin")
    if os.path.exists(main_file):
        # print(f"Removing {main_file}")
        delete_file(main_file)

    for gcov_file in glob.iglob(f'{target_dir}/**/*.gcda', recursive=True):
        # print(f"Removing {gcov_file}")
        delete_file(gcov_file)

    main_o_fp = os.path.join(target_dir, "main.o")
    if os.path.exists(main_o_fp):
        delete_file(main_o_fp)

    main_gcno_fp = os.path.join(target_dir, "main.gcno")
    if os.path.exists(main_gcno_fp):
        delete_file(main_gcno_fp)


def run_system_tests_on_user_bin(source_dir, test_dir, show_flag=False, case_sensitive=False):
    # test_cases = [os.path.join(test_dir, file) for file in os.listdir(test_dir) if file.endswith(".json")]
    test_cases = sorted(
        [os.path.join(test_dir, file) for file in os.listdir(test_dir) if file.startswith("stest") and file.endswith(".json")],
        key=extract_numbers_for_sorting
    )

    passes = 0
    failures = 0
    test_count = len(test_cases)
    for test_json_file in test_cases:
        hidden_test = False
        if "hidden" in test_json_file:
            hidden_test = True
        if run_test(source_dir, test_dir, test_json_file, case_sensitive=case_sensitive, hidden_test=hidden_test):
            passes += 1
        else:
            failures += 1
            if os.getenv("TEST_ALL", "") == "":
                print("")
                if passes > 0:
                    print(f"The program passed {passes} tests of {test_count}")
                print(f"{RED}Failed System Test {os.path.basename(test_json_file)} {RESET_COLOR} ")

                return failures, passes, test_json_file

    return failures, passes, None


def is_elf_binary(file_path):
    try:
        with open(file_path, 'rb') as file:
            magic = file.read(4)
            if magic == b'\x7fELF':
                return True
            else:
                return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False


def kill_process(process_name):
    try:
        # Use pkill to terminate the process
        subprocess.run(["pkill", "-f", process_name], check=True)
        time.sleep(1)
        print(f"A previous running process {process_name} has been terminated.")
    except subprocess.CalledProcessError:
        # usually this will happen
        # print(f"The process {process_name} was not running")
        pass
    except Exception as e:
        print(f"An error occurred: {e}")


def verify_users_main(source_dir):
    target_path = os.path.join(source_dir, "main.bin")

    if not os.path.exists(target_path) :
        print(f"The file {target_path} does not exist.\nPlease compile the source code to create the file with the option `-o {target_path}` ")
        return False 

    if (os.path.exists(target_path) and not is_elf_binary(target_path)) :
        print(f"The {target_path} is not a compiled binary.\nPlease compile the source code to create the file with the option `-o {target_path}` ")
        return False 
    return True 


def log_test_run(passes, test_count):
    try :
        if ED_ENV:
            return
        inter_log_fp = "/home/hacker/.local/share/ultima/inter.dat"
        current_datetime = datetime.now()
        iso_format_datetime = current_datetime.isoformat()
        if os.path.exists(LEVEL_CONFIG_FP):
            with open(LEVEL_CONFIG_FP) as cf:
                level_config = json.load(cf)
            with open(inter_log_fp, "a+") as wf:
                pname = os.path.basename(level_config.get('hwdir', ''))
                level = level_config.get('level', '')
                wf.write(f"{iso_format_datetime}: {pname}-{level} : T {passes}p of {test_count}\n")
        else:
            with open(inter_log_fp, "a+") as wf:
                wf.write(f"{iso_format_datetime}: Unknown : Tester {passes}p of {test_count}\n")
        os.chmod(inter_log_fp, os.stat(inter_log_fp).st_mode | 0o666)

    except Exception as ex:
        with open("/home/hacker/.local/share/ultima/err.dat", "a+") as wf:
            wf.write(f"Error writing to inter, {ex}")


def check_for_execution(source_dir):
    main_gcda_fp = os.path.join(source_dir, "main.gcda")
    main_gcno_fp = os.path.join(source_dir, "main.gcno")
    if os.path.exists(main_gcno_fp) and os.path.exists(main_gcda_fp) :
        return True

    # no execution but build created gcno files
    if os.path.exists(main_gcno_fp) and not os.path.exists(main_gcda_fp) :
        print(f"You have not executed your program yet, you must execute it with input each time before running tester. ")
        print(f"After compiling in the terminal, run your program by entering ./main.bin ")
        # TODO: lookup up last test and suggest they run it with that input
        print("If you previously, failed a test, be sure to test your program with that input before re-running tester")
        if os.path.exists(os.path.join(source_dir, "main.bin-main.gcda")) or os.path.exists(os.path.join(source_dir, "main.bin-data.gcda")):
            if os.path.exists(os.path.join(source_dir, "Makefile")):
                print("\nThe tester has detected an issue with the submitted files, likely due to attempts to compile the binary ")
                print("using gcc directly instead of using make. To correct this problem, please do the following: ")
                print("\t1. run make clean\n\t2. run make\n\t3. execute and test your program.")            
        return False 
    elif not os.path.exists(main_gcno_fp):

        make_fp = os.path.join(source_dir, "Makefile")
        mf_contents = ""
        if os.path.exists(make_fp):
            with open(make_fp, "r") as rf:
                mf_contents = rf.read()
            if "ftest-coverage" not in mf_contents or "fprofile-arcs" not in mf_contents:
                print("The Makefile template was improperly altered and it is no longer enabling coverage checking; as a result, you cannot pass the tests. ")
                if "BASE_CFLAGS" not in mf_contents:
                    print("The Makefile has been irrepreably changed, you must copy the template Makefile located at /challenge/template/Makefile and then add the values for the OBJ variable and the dependencies.")
                elif "$(CC) $(CFLAGS)" not in mf_contents and "$(CXX) $(CFLAGS)" not in mf_contents:
                    print("The Makefile has been irrepreably changed, you must copy the template Makefile located at /challenge/template/Makefile and then add the values for the OBJ variable and the dependencies.")
                else:
                    print("To fix the issue verify that BASE_CFLAGS looks as follows\n\tBASE_CFLAGS = -Wall -Werror -g -ftest-coverage -fprofile-arcs")
                    print("After adding the coverage flags that, do a make clean, a make, and then execute your program. If you do an ls in the terminal you should have files with the extension .gcda and .gcno")
            else:
                print(f"Tester expected to find the file {main_gcno_fp} but it did not, please run make clean and make again. If the problem persists it is either a bug or a problem with your configuration please contact the course staff. ")
        else:
            print("Compile your program using the command \n\tgcc main.c -o main.bin \nMake sure you are only using 'gcc' in the command and not the full path to a gcc version. If the problem persists, it might be bug or a problem with your configuration, please contact the course staff.")
        return False 
    else:
        print("Found proof of execution")
    return True


def delete_file(file_path):
    try:
        os.remove(file_path)
        # print(f"File {file_path} has been deleted successfully.")
    except FileNotFoundError:
        print(f"The file {file_path} does not exist.")
    except PermissionError:
        print(f"Permission denied: unable to delete {file_path}.")
    except Exception as e:
        print(f"Error deleting the file: {e}")


def check_for_codecoverage(source_dir, minimum_code_coverage=20):

    c_files = glob.iglob(f'{source_dir}/**/*.c', recursive=True)
    cpp_files = glob.iglob(f'{source_dir}/**/*.cpp', recursive=True)
    try:
        # clean up gcov files before recreating
        for f in glob.iglob(f'{source_dir}/**/*.gcov', recursive=True):
            delete_file(f)

        cmd = ["gcov"]
        cmd.extend(c_files)
        cmd.extend(cpp_files)
        # print(cmd)
        result = subprocess.run(cmd, cwd=source_dir, capture_output=True, text=True, check=False)

        match = re.search(r'Line.*:(\d+\.\d+)%', result.stdout.splitlines()[-1])
        if match:
            coverage = float(match.group(1))
            print(f"Code coverage is {coverage}%")
            if coverage < minimum_code_coverage:
                print(f"Error: Code coverage is below the minimum required coverage of {minimum_code_coverage}%")
                print(f"Current code coverage is {coverage}%")
                if os.path.exists("/home/me") or os.path.exists("/challenge/model/data.h"):
                    print("Exception for Staff on code coverage requirement, passing test")
                    return True 
                return False 
        else:
            print(f"Error: Could not determine code coverage")
            print(f"Output was: {result.stdout}")
            return False 
    except subprocess.CalledProcessError as e:
        print(f"Error running gcov: {e}")
        return False 

    return True

def xor_string(input_string, key):
    # Ensure the XOR result is within the valid byte range
    xor_bytes = bytes([(ord(char) ^ key) % 256 for char in input_string])
    # Convert the XORed bytes into a Base64 string
    base64_string = base64.b64encode(xor_bytes).decode('utf-8')
    return base64_string

def is_stripped(binary_path):
    try:
        # Use readelf to check for the presence of the .symtab section
        result = subprocess.run(["readelf", "-S", binary_path], capture_output=True, text=True)
        if ".symtab" not in result.stdout:
            return True
        return False
    except Exception as e:
        print(f"An error occurred while checking if the binary is stripped: {e}")
        return False

def run_tests(args, system_test_dir):

    show_flag = True
    user_created_system_test = False
    level_config = None
    performCompile = True
    case_sensitive = False
    initial_files = None
    module_id = None
    level_id = None
    if args.source_dir and system_test_dir is not None:
        source_dir = args.source_dir
        show_flag = False
    elif os.path.exists(LEVEL_CONFIG_FP):

        with open(LEVEL_CONFIG_FP) as cf:
            level_config = json.load(cf)
        module_id = os.path.basename(level_config.get("hwdir", ""))
        level_id = int(level_config.get('level', '0'))
        show_flag = level_config.get("testerShowsFlag", True)
        performCompile = level_config.get("performCompile", True)
        other_compile_args = level_config.get("otherCompileArgs", [])
        codecoverage = level_config.get("codecoverage", 0)
        checkForExecution = level_config.get("checkForExecution", False)
        case_sensitive = level_config.get("caseSensitive", False)
        initial_files = level_config.get("initial_files", None)
        user_created_system_test = level_config.get("user_created_system_test", False)
        if os.path.exists(level_config.get('testdir',"")):
            system_test_dir = level_config["testdir"]


        # if source_dir is provided in level.json then use it otherwise use hwdir + level
        source_dir = level_config.get("source_dir", "")
        if len(source_dir) == 0:
            source_dir = os.path.join(level_config["hwdir"], level_config.get("level", "01"))
            if not os.path.exists(source_dir):
                source_dir = os.path.join(level_config["hwdir"])
                if not os.path.exists(source_dir):
                    if os.path.exists("/home/system_tests"):
                        source_dir = "/home"
                    

        if level_config.get("requireUsersMain", False):
            if not verify_users_main(source_dir):
                save_results(source_dir, -1,-1, initial_files, module_id, level_id, "No main.bin found")
                sys.exit(123)

        if checkForExecution:
            if not check_for_execution(source_dir):
                save_results(source_dir, -1,-1, initial_files, module_id, level_id, "No execution done between calls")
                if os.path.exists(os.path.join(source_dir, "Makefile")):
                    if os.path.exists(os.path.join(source_dir, "main.bin-main.gcda")) or os.path.exists(os.path.join(source_dir, "main.bin-data.gcda")):
                        print(f"{RED}An error with detecting the program's execution has occurred. Please follow the instructions above to resolve this error.  {RESET_COLOR}")    
                    else:
                        print(f"{RED}Error: the main.bin program has not been executed since its last compile. Please execute and test your program before submitting to the tester {RESET_COLOR}")
                else:
                    print(f"{RED}Error: the main.bin program has not been executed since its last compile. Please execute and test your program before submitting to the tester {RESET_COLOR}")
                sys.exit(100)
        if codecoverage > 0:
            if check_for_codecoverage(source_dir, codecoverage):
                pass 
                # all good, continue on little soldier
            else:
                save_results(source_dir, -1,-1, initial_files, module_id, level_id, "code coverage check failed")
                sys.exit(221)

    else:
        return False

    total_failures = 0
    total_passes = 0

    compile_success = False
    compiled_users_code = False
    if source_dir != "/challenge/model":
        if performCompile:
            compile_success = compile_program(source_dir, other_compile_args=other_compile_args)
            compiled_users_code = True
        else:
            compile_success = True
        if os.path.exists(os.path.join(source_dir, "main.bin")):
            source_main_bin = os.path.join(source_dir, "main.bin")
            system_test_main_bin = os.path.join(SYSTEM_TESTS_DIR, "main.bin")
            if (os.path.exists(source_main_bin)):
                kill_process(system_test_main_bin)
                kill_process(source_main_bin)
                shutil.copy(source_main_bin, system_test_main_bin)
                md5_chk = calculate_md5(system_test_main_bin)
                print(f"Copied {source_main_bin} to {system_test_main_bin} for system testing, with an md5 of {md5_chk}")
                if os.path.exists("/challenge/modelGood.bin"):
                    mg_md5 = calculate_md5("/challenge/modelGood.bin")
                    if md5_chk == mg_md5:
                        print(f"ModelGood.bin and main.bin are the same, stop trying to find ways to cheat and just work on the assignment. This attempt will be reported to the professor.")
                        (source_dir, -1, -1, initial_files, module_id, level_id, "")
                        save_test_results(source_dir, -1, -1, module_id, level_id, "", error_message = "Attmpted to use modelGood.bin as main.bin")
                        sys.exit(124)
                
                # Check if the binary is stripped
                if is_stripped(source_main_bin):
                    print(f"{RED}Error: You have either attempted to treat modelGood.bin as your own program or you stripped main.bin, if cheating then stop, if stripping then stop that too.{RESET_COLOR}")
                    sys.exit(125)
    else:
        # if we aren't doing a compile we will still want to run system tests, level-01-13
        compile_success = True



    if level_config is not None:
        usertests = level_config.get("requiredUserTests",[])
        for utest_id, ut_path in enumerate(usertests):
            if "<hwdir>" in ut_path:
                ut_path = ut_path.replace("<hwdir>", source_dir + "/")
                usertests[utest_id] = ut_path

        print(f"{usertests}")
        if not verify_user_tests_unique(usertests, system_test_dir):
            print("Please fix user test case")
            save_results(source_dir, -1, -1, initial_files, module_id, level_id, "")
            sys.exit(192)

        if len(usertests) > 0:
            print("---------------[  User Tests  ]---------------")

        for ut in usertests:
            resfail, respass = run_user_tests(source_dir, compile_success, compiled_users_code, ut, case_sensitive=case_sensitive)
            total_failures += resfail
            total_passes += respass
        if len(usertests) > 0:
            print("")

    last_test_json_fp = ""
    if compile_success and os.path.exists(SYSTEM_TESTS_DIR):
        print("---------------[ System Tests ]---------------")
        resfail, respass, last_test_json_fp = run_system_tests_on_user_bin(source_dir, system_test_dir, case_sensitive=case_sensitive)
        total_failures += resfail
        total_passes += respass

    if user_created_system_test:
        print('Flag will be in output of program, test case must include `"print_output": true`')
    elif total_failures == 0 and total_passes > 0:
        print(f"\nAll {total_passes} Tests Passed ")
        if ED_ENV:
            print("Copy this value to your clipboard and run ed_credit on pwn.college")
            #name = os.getenv("ED_USER_NAME")
            key = int(os.getenv("ED_USER_ID"))
            
            with open(LEVEL_CONFIG_FP, "r") as cf:
                level_config = json.load(cf)

            data = f"{key},{level_config['labid']},{level_config['level']}"
            print(xor_string(data, key))
        else:
            log_test_run(total_passes, total_passes+total_failures)
            print("Congrats, here's your flag")
            flag = None
            if show_flag:
                with open("/flag", "r") as ff:
                    flag = ff.read()
                    print(f"{GREEN}{flag}{RESET_COLOR}")
            else:
                print("pwn.college{...")
                print("No flag, must run without using either --source-dir and --test-dir, only works when default directory under /home/hacker/cse240 is used")
            save_results(source_dir, total_passes, total_failures, initial_files, module_id, level_id, flag)
    elif total_failures == 0 and total_passes == 0:
        print("Error: No failures or passes recorded, this is likely a bug, please report to course staff.")
    else:
        print(f"\nSummary: {total_passes} tests passed, {RED}{total_failures} {RESET_COLOR}tests failed")
        log_test_run(total_passes, total_passes+total_failures)

        print(f"{RED}Too many failures{RESET_COLOR} to receive flag")
        save_results(source_dir, total_passes, total_failures, initial_files, module_id, level_id, last_test_json_fp=last_test_json_fp)
        clean_up(source_dir)

    return True


def run_user_tests(source_dir, compile_success, compiled_users_code, ut, case_sensitive=False):
    failures = 0
    passes = 0
    module_num, level_num, test_num = extract_numbers(ut)
    model_good = os.path.join(CHALLENGE_DIR, "modelGood.bin")
    model_bad = os.path.join(CHALLENGE_DIR, f"modelBad{module_num}.{level_num}.{test_num}.bin")

    # the expectation is that the test will fail when running with model_bad, so we invert using expect_failure
    if run_test(source_dir, os.path.dirname(ut), ut, model_bad, expect_failure=True, case_sensitive=case_sensitive):
        passes += 1
    else:
        failures += 1

    if run_test(source_dir, os.path.dirname(ut), ut, model_good, case_sensitive=case_sensitive):
        passes += 1
    else:
        failures += 1
    if compile_success and compiled_users_code:
        users_main_bin = os.path.join(source_dir, "main.bin")
        if run_test(source_dir, os.path.dirname(ut), ut, users_main_bin, case_sensitive=case_sensitive):
            passes += 1
        else:
            failures += 1

    return failures, passes


def main():


    parser = argparse.ArgumentParser(description="C/C++ Program Tester")
    parser.add_argument("--source_dir", "--source-dir", "-s", help="Directory containing the source files")
    parser.add_argument("--test_dir", "--test-dir", "-t", help="Directory containing the test files")

    args = parser.parse_args()

    if  args.test_dir:
        test_dir = args.test_dir
    elif os.path.exists(SYSTEM_TESTS_DIR):
        test_dir = os.path.join(SYSTEM_TESTS_DIR)
    else:
        test_dir = None

    init_db()
    
    if not run_tests(args, test_dir):
        print(f"For the tester to run there must be a level config file located under {LEVEL_CONFIG_FP} or the --source-dir and --test-dir options must be added ")
        parser.print_usage()
        sys.exit(10)


if __name__ == "__main__":
    main()
