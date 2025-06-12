#! /usr/bin/env python3
import os
import subprocess
import json
import sys
import random
import string

def find_tests_file():
    # Get the directory where the Python script is located
    script_directory = "/challenge"  if os.path.exists("/challenge") else os.getcwd()

    # List all files in that directory
    files_in_directory = os.listdir(script_directory)

    # Iterate through the files
    for filename in files_in_directory:
        if "tests" in filename and filename.endswith("json"):
            return os.path.join(script_directory, filename)
    return None

def generate_random_string(length=8):
    characters = string.ascii_letters + string.digits  # Combines lowercase, uppercase letters and digits
    return ''.join(random.choice(characters) for _ in range(length))

class TestCaseRunner:

    def __init__(self, test_file, source_file):
        with open(test_file, 'r') as f:
            self.test_cases = json.load(f)
        self.source_file = source_file
        self.binary_fp = os.path.join("/tmp", generate_random_string(8))
        self.testcnt = 1

    def compile_source(self):

        compile_cmd = f"gcc {self.source_file} -o {self.binary_fp} -Werror"
        output, ret, err  = self.log_and_exec(compile_cmd)

        if ret != 0:
            print(output)
            print(err)
            print(f"return code = {ret}")
            self.log_neg("Compilation failed!")
            exit(1)


    def log_and_exec(self, command, stdin_content=""):
        print(f"\033[38;5;8m{command}\033[0m")
        stdin_pipe = subprocess.PIPE
        stdout_pipe = subprocess.PIPE
        process = subprocess.Popen(command, stdin=stdin_pipe, stdout=stdout_pipe, stderr=subprocess.PIPE, shell=True)
        if stdin_content != "":
            output, error = process.communicate(input=stdin_content.encode())
        else:
            output, error = process.communicate()

        return output.decode(), process.returncode, error.decode()

    def log_pos(self, message):
        # \t${testcnt}. \033[38;5;10m✔ ️$msg\033[0m\n
        print(f"\t{self.testcnt}. \033[38;5;10m✔ {message}\033[0m")
        self.testcnt += 1

    def log_neg(self, message):
        print(f"\n\033[38;5;9m{message}\033[0m\n")

    def run_test(self, test):

        command = f"{self.binary_fp} {test.get('param_input', '')}"
        stdin_content = test.get("stdin", "")
        expected_output = test.get("expected_output", "")
        expected_return = test.get("expected_return", None)
        pos_response = test.get("positive_response", "")
        neg_response = test.get("negative_response", "")

        output, ret, err = self.log_and_exec(command, stdin_content)

        if expected_return is not None and expected_return != ret:
            print(output)
            print(err)
            self.log_neg(neg_response)
            exit(1)

        if expected_output.lower() not in output.lower():
            print(output)
            print(err)
            self.log_neg(neg_response)
            exit(1)

        self.log_pos(pos_response)

    def run(self):
        for test in self.test_cases:
            self.run_test(test)
        print("All test cases passed.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Please provide the location of the source code.")
        exit(1)
    source_file = sys.argv[1]

    test_case_filename = find_tests_file()
    runner = TestCaseRunner(test_case_filename, source_file)
    runner.compile_source()
    runner.run()
