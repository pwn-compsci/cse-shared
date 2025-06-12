#!/usr/bin/env python3
import base64

import argparse
import difflib
import json
import os
import re
import random
import shutil
import subprocess
import sys
import time

RED = '\033[31m'
BLUE = '\033[1;94m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
ORANGE = '\033[38;5;208m'
DARK_GREY = '\033[1;30m'
RESET_COLOR = '\033[0m'

# pylint: disable = trailing-whitespace
# pylint: disable = line-too-long
# pylint: disable = unspecified-encoding
# pylint: disable = missing-function-docstring

OUTPUT_FILE_LINE_LIMIT = 20


def normalize_whitespace_and_case(text, case_sensitive=False):
    if case_sensitive:
        return ' '.join(text.split())
    else:
        return ' '.join(text.split()).lower()


def run_icdiff(expected_file, actual_file, tmp_test_diff_results):

    with open(tmp_test_diff_results, 'w') as f:
        try:
            cmd = ["icdiff", "-N"]
            if os.environ.get("COLS", 0) == 0:
                cmd = cmd + ["--cols", "100"]
            cmd += [expected_file, actual_file]
            result = subprocess.run(cmd, text=True, capture_output=True)
            f.write(result.stdout)
            if result.stdout:
                output_lines = result.stdout.splitlines()
                if len(output_lines) > OUTPUT_FILE_LINE_LIMIT:
                    output = "\n".join(output_lines[:OUTPUT_FILE_LINE_LIMIT]) + f"\n... truncated see the rest in {tmp_test_diff_results}"
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
                        if match_ratio > highest_ratio:
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
            if match.size > 3 and matcher.ratio() > highest_ratio:
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
    for expected_line in expected_lines:
        # for actual_line in actual_iter:
        
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
            actual_index+=1
        else: # if it completes
            output_match_report["missing"].append(expected_line)
            closest_index, highlighted_text, marker = find_closest_match(expected_line, actual_lines, regex=(output_type=="regex"))

            if (closest_index is not None):
                output_match_report['closestMatchIndex'] = closest_index
                if last_actual_index > closest_index:
                    output_match_report["closestMatch"] = f"It appears the expected text {highlighted_text} is being found in the wrong order. Recheck test case and your program's output for order of results."
                else:
                    output_match_report["closestMatch"] = highlighted_text
                output_match_report["closestMarker"] = marker
            # let's only find one missing thing
            break



    output_match_report["passed"] = len(output_match_report["unexpected"]) == 0 and len(output_match_report["missing"]) == 0

    return output_match_report


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


def file_output_failed_test_information(target_path, test, args, input_data, expected_output_list, test_name, test_description, check_file, actual_output_list, out_match_report, case_sensitive=False, start_time=None):
    tmp_test_outputdir = os.path.join("/tmp", "test_output")
    os.makedirs(tmp_test_outputdir, mode=0o755, exist_ok=True)

    failed_test_message(target_path, args, input_data, test_name, test_description, start_time, expected_output=expected_output_list, message=f"missing output in {check_file}")

    if out_match_report["matchesFound"] > 0:
        print(f"\tMatches found    : {GREEN}{out_match_report['matchesFound']} {RESET_COLOR}out of {len(expected_output_list)}")

    if len(out_match_report["missing"]) > 0:
        print(f"\tMissing from file: {ORANGE}" + ', '.join(out_match_report["missing"]) + RESET_COLOR)

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
    print("")


def output_failed_test_information(target_path, test, args, input_data, expected_output_list, test_name, test_description, actual_output_list, out_match_report, case_sensitive=False, start_time=None):
    tmp_test_outputdir = os.path.join("/tmp", "test_output")
    os.makedirs(tmp_test_outputdir, mode=0o755, exist_ok=True)

    failed_test_message(target_path, args, input_data, test_name, test_description, start_time, expected_output=expected_output_list)
    closestMatchExist = False
    if out_match_report["matchesFound"] > 0:
        print(f"\tMatches found: {GREEN}{out_match_report['matchesFound']} {RESET_COLOR}out of {len(expected_output_list)}")

    if len(out_match_report["missing"]) > 0:
        if 'closestMatchIndex' in out_match_report:
            lineno = f"{out_match_report['closestMatchIndex']+1}"
            print(f"\tFailed to find in output {' ' * len(lineno)} : {ORANGE}" + ', '.join(out_match_report["missing"]) + RESET_COLOR)
            print(f"\tClosest match is at line {lineno} : {out_match_report['closestMatch']}")
            closestMatchExist = True
        else:
            print(f"\tFailed to find in output: {ORANGE}" + ', '.join(out_match_report["missing"]) + RESET_COLOR)

    if len(out_match_report["unexpected"]) > 0:
        print(f"\tShould not have found in output: {RED}" + ', '.join(out_match_report["unexpected"]) + RESET_COLOR )
        print(f"\tUnexpected output found using: {ORANGE}" + ', '.join(out_match_report["unexpectedToken"]) + RESET_COLOR )

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
            print(f"{DARK_GREY}...skipping (get the full output using `cat <filename>` )...{RESET_COLOR}")
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
            print(f"{DARK_GREY}...skipping (get the full output using `cat <filename>` )...{RESET_COLOR}")

    elif len(out_match_report["unexpected"]) > 0:
        env_vars = os.environ.copy()          # Start with a copy of the current environment
        env_vars['GREP_COLORS'] = 'mt = 01;31'  # Add or modify the environment variables

        print(f"--------<[ {test} Unexpected token found in output located at {preprocessed_actual_filename}) ]>--------")
        if (len(actual_output_list) > OUTPUT_FILE_LINE_LIMIT):
            print(f"{DARK_GREY}...skipping lines, get the full output using: cat {preprocessed_actual_filename}{RESET_COLOR}")
            cmd=["grep", "--color = auto", "-n", "-A10", "-B10", "-P", out_match_report["unexpectedToken"][0], preprocessed_actual_filename]
            subprocess.run(cmd, env=env_vars)
            print(f"{DARK_GREY}...skipped lines ...{RESET_COLOR}")
        else:
            cmd=["grep", "--color = auto", "-n", "-P", out_match_report["unexpectedToken"][0]+"|(?=.)", preprocessed_actual_filename]
            subprocess.run(cmd, env=env_vars)

    else:
        print(f"--------<[ {test} Diff b/t Expected and Actual  ({tmp_test_outputdir}/{test}.diff) ]>--------")
        tmp_test_diff_results = os.path.join(tmp_test_outputdir, f"{test}.diff")
        run_icdiff(preprocessed_expected_filename, preprocessed_actual_filename, tmp_test_diff_results)

    print(f"{DARK_GREY}↑ EOF ↑{RESET_COLOR}")
    print("")


def failed_test_message(target_path, args, input_data, test_name, test_description, start_time=None, expected_output=None, message=""):
    print(f"{RED}FAIL{RESET_COLOR} {test_name} {message}")
    formmated_args = []
    for param in args:
        if ' ' in param:
            # Surround parameters with spaces in single quotes
            formmated_args.append(f"'{param}'")
        else:
            formmated_args.append(param)

    print(f"\tTest Desc        : {test_description}")
    print(f"\tCommand          :{BLUE} {' '.join([target_path])} {' '.join(formmated_args)}{RESET_COLOR}")

    print(f"\tProgram Input    : {repr(input_data)}")
    if expected_output is not None:
        print(f"\tExpected Output  : {expected_output}")
    if start_time is not None:
        print(f"\tTest ran in      : {time.time()-start_time:.2f}s")


def pick_random_word(file_path):
    try:
        with open(file_path, 'r') as file:
            words = file.read().splitlines()
            if not words:
                return "No words found in the file."
            return random.choice(words)
    except FileNotFoundError:
        return ""


def run_target_program(test, working_directory, target_path, args, input_data, model_program=False, environmentVar=None, return_code=0, expected_output=None, hidden_test=None ):
    try:
        timeout_command = ['timeout', '-k','2', '10']
        command = timeout_command + [target_path] + args
        # print("[run_target_program] " +" ".join(command))
        # print(f"[run_target_program]  {source_dir}")
        # print(f"[run_target_program] {input_data}")
        # print(f"[run_target_program] {environmentVar=}")
        
        environmentVar.update(os.environ)
        do_check = return_code == 0

        result = subprocess.run(command, cwd=working_directory, input=input_data, text=True, encoding='latin-1',
                                capture_output = True, timeout = 3, check = do_check, env = environmentVar)
        if result.returncode == 124:
            raise subprocess.TimeoutExpired("timeout caught it", 10)
        if not do_check:
            result.returncode == return_code

    except subprocess.TimeoutExpired:
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

        print(f"\n{test}: {YELLOW}Execution ERROR while running {os.path.basename(target_path)} {RESET_COLOR}")
        import traceback
        traceback.print_exc(ex)

        if (model_program):
            print("\nTry again if it occurrs again, please contact support via Discord")

        sys.exit(121)

    actual_output = result.stdout
    if (len(result.stderr) > 0):
        actual_output = result.stdout + "-"*100 + "\n" + result.stderr

    return actual_output


def nonprintable_test(target_path, args, input_data, test_name, test_description, actual_output, start_time):
    non_printable_regex = re.compile(r'[^\x20-\x7E\n\t\r]')
    if non_printable_regex.findall(actual_output):
        failed_test_message(target_path, args, input_data, test_name, test_description, start_time=start_time)

        print("Output contains non-printable characters. This is usually caused by using a c-string that's not terminated with a NULL ")
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
            subprocess.run(cmd, check = True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed reset command {cmd} with return code {e.returncode}\n{e.stdout}\n{e.stderr}")
            sys.exit(102)


# Get the list of test files and sort them numerically


def run_test(source_dir, test_dir, test_json_file, target_path=None, expect_failure=False, case_sensitive=False):

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

    target = test_json.get("target", "")

    if "main.bin" not in target:
        target_path = shutil.which(target)
        if not os.path.exists(target_path):
            print(f"Unable to find target, {target}")
            sys.exit(133)

    if target_path is None:
        target_path = os.path.join(source_dir, "main.bin")

    if len(reset_commands) > 0:
        run_reset_commands(reset_commands)

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
            tmp_test_outputdir = os.path.join("/tmp", f"test_output")
            os.makedirs(tmp_test_outputdir, mode=0o755, exist_ok=True)
            test_file = os.path.join(tmp_test_outputdir, f"{test}_data_{os.path.basename(filepath)}")
            shutil.copy(filepath, test_file)

    args = [a.replace("<testsdir>", test_dir + "/").replace("<sourcedir>", source_dir + "/")
            for a in test_json.get("args",[])]

    input_data = test_json.get("input", "")

    if isinstance(input_data, list):
        input_data = '\n'.join(input_data)
    input_data += "\n"

    expected_output_list = test_json.get("output", [])

    expected_output_list = [string for string in expected_output_list if string.strip()]

    return_code = test_json.get("returnCode", 0)
    start_time = time.time()
    actual_output = run_target_program( test, working_dir, target_path, args, input_data, environmentVar=test_json.get("testEnvironmentVars",{}),
                                       return_code = return_code, expected_output = expected_output_list)

    test_name = test_json.get('name','')
    test_description = test_json.get('description','')

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
            failed_test_message(target_path, args, input_data, test_name, test_description, start_time)
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
                file_output_failed_test_information(target_path, test, args, input_data, expected_file_out_list, test_name, test_description, check_filepath, actual_lines_in_file_list, file_out_report, case_sensitive=case_sensitive, start_time=start_time)
                return False

        out_match_report = match_output(expected_output_list, actual_output_list,  test_json.get("unexpectedOutput",[]), output_type, case_sensitive=case_sensitive)

        if (out_match_report["passed"] and expect_failure == False) or (not out_match_report["passed"] and expect_failure==True):
            print(f"{GREEN}\u2714 PASS{RESET_COLOR} {test_name} ran in {time.time()-start_time:.2f}s")
            if test_json.get("print_output", False):
                print(f"Output for {test}")
                print(actual_output);
            return True
        else:
            output_failed_test_information(target_path, test, args, input_data, expected_output_list, test_name, test_description, actual_output_list, out_match_report, case_sensitive=case_sensitive, start_time=start_time)
            return False
    return False


def run_system_tests_on_user_bin(source_dir, test_dir, show_flag=False, case_sensitive=False):
    # test_cases = [os.path.join(test_dir, file) for file in os.listdir(test_dir) if file.endswith(".json")]
    test_cases = sorted(
        [os.path.join(test_dir, file) for file in os.listdir(test_dir) if file.startswith("stest") and file.endswith(".json")],
        key = extract_numbers_for_sorting
    )

    passes = 0
    failures = 0

    for test_json_file in test_cases:
        if run_test(source_dir, test_dir, test_json_file, case_sensitive=case_sensitive):
            passes += 1
        else:
            failures += 1
    return failures, passes


def xor_string(input_string, key):
    # Ensure the XOR result is within the valid byte range
    xor_bytes = bytes([(ord(char) ^ key) % 256 for char in input_string])
    # Convert the XORed bytes into a Base64 string
    base64_string = base64.b64encode(xor_bytes).decode('utf-8')
    return base64_string


def run_tests(args, source_dir, system_test_dir):

    total_failures = 0
    total_passes = 0

    resfail, respass = run_system_tests_on_user_bin(source_dir, system_test_dir, case_sensitive=False)
    total_failures += resfail
    total_passes += respass

    if total_failures == 0 and total_passes > 0:
        print(f"\nAll {total_passes} Tests Passed ")
        key = 0
        if os.path.exists("key"):
            with open("key", "r") as rf:
                line = rf.readline().strip()  # Read the first line and strip newline characters
            if len(line) == 0:
                print(f"{RED}Error, no value in key file, get key value from course staff, cannot give solution string {RESET_COLOR}")
                sys.exit(132)

            # Check if the line is an integer
            if line.isdigit():
                # Convert to integer
                key = int(line)
            else:
                # Convert each character to its ASCII value and concatenate
                key = int(''.join(str(ord(char)) for char in line))

        if key > 0:
            print("Copy this value to pwn.college")
            name = os.getenv("ED_USER_NAME")
            data = {"p": "Google Ascender Nation", "n": name}
            print(xor_string(json.dumps(data), key))

    else:
        print(f"\nSummary: {total_passes} tests passed, {RED}{total_failures} {RESET_COLOR}tests failed")
        print(f"{RED}Too many failures{RESET_COLOR} to receive flag")
    return True


def main():

    parser = argparse.ArgumentParser(description="C/C++ Program Tester")

    args = parser.parse_args()

    home_dir = os.path.expanduser("~")

    if os.path.exists("/home/.config/level.json"):
        with open("/home/.config/level.json", "r") as rf:
            jdata = json.load(rf)
        source_dir = jdata.get("groupLabSourceDir", "/home")
        test_dir = jdata.get("groupLabTestDir", "/home/tests")
    elif os.path.exists(os.path.join(test_dir, "tests")):
        test_dir = os.path.join(home_dir, "tests")
        source_dir = os.path.join(home_dir)
    else:
        test_dir = home_dir
        source_dir = home_dir

    if not os.path.exists(source_dir) or not os.path.exists(test_dir):
        print("Error, for some reason the source dir or test dir cannot be found, contact Professor or a TA")
        exit(42)


    if not os.path.exists(os.path.join(source_dir, "main.bin")) and not os.path.exists(os.path.join(test_dir, "main.bin")):
        print("Error, the program must be compiled before the tests can be run. ")
        exit(102)

    run_tests(args, source_dir, test_dir)


if __name__ == "__main__":

    main()