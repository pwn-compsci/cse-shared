#! /opt/pwn.college/python

import os
import re
import random
import string
import subprocess
import atexit
from pygments import highlight
from pygments.lexers import CLexer
from pygments.formatters import Terminal256Formatter


UTFBLANKS = ['\u2008','\u2009','\u205f','\u3000']


def cleanup_compiled_file(compiled_file):
    # Clean up the compiled file if it exists
    if os.path.exists(compiled_file):
        os.remove(compiled_file)


def compare_strings(expected, actual):
    # Compare the strings character by character
    for i, (c1, c2) in enumerate(zip(expected, actual)):
        if c1 != c2:
            return i
    return min(len(expected), len(actual))


# print the c_code using the pygments lexer and highlighter
def print_c_code(c_code):
    lexer = CLexer()
    formatter = Terminal256Formatter(style='monokai')
    highlighted_code = highlight(c_code, lexer, formatter)
    highlighted_code = highlighted_code.replace(" ", random.choice(UTFBLANKS))
    highlighted_code = re.sub(r'#([a-zA-Z]*)(.*)', r'// #️ ⃣ \1 \2', highlighted_code)
    print(highlighted_code)


def compile_and_run_c(filename):
    # Read the C source code from the file
    with open(filename, 'r') as file:
        c_code = file.read()

    print_c_code(c_code)

    # Generate a random 8-character file name for the compiled file
    compiled_file = ''.join(random.choices(string.ascii_letters + string.digits, k=8)) + '.bin'
    compiled_file = os.path.join('/tmp', compiled_file)

    # Compile the C code
    compile_command = f"gcc {filename} -o {compiled_file}"
    compile_result = os.system(compile_command)

    if compile_result != 0:
        print("Compilation failed. Please check your C code.")
        return

    # Set the file permissions to read-only for the owner
    os.chmod(compiled_file, 0o700)

    # Register the cleanup function to be called on script exit
    atexit.register(cleanup_compiled_file, compiled_file)

    # Run the compiled C program
    try:
        output = subprocess.check_output([compiled_file]).decode().strip()
    except subprocess.CalledProcessError as e:
        print(f"Error occurred during execution: {e}")
        return

    # Ask the user to enter the expected output
    expected_output = input("Enter the expected output from the C program: ").strip()

    # Check if the output matches the expected output
    if output == expected_output:
        print(f"Execution '{expected_output}' matches! Great job!")
        return True
    else:
        position = compare_strings(expected_output, output)
        print(f"Mismatch occurred at position: {position}")
        print(f"Yours  : '{expected_output[:position + 1]}'")
        print(f"Actual : '{output[:position]}\033[38;5;9m❌\033[0m'")
        return False


if __name__ == "__main__":
    # Assuming you provide the filename as a command line argument
    import sys

    if len(sys.argv) != 2:
        print("Usage: python3 script_name.py c_file_name.c")
    else:
        c_file_name = sys.argv[1]
        res = compile_and_run_c(c_file_name)
        if res:
            try:
                with open("/flag", 'r') as blob_file:
                    print(blob_file.read())
            except FileNotFoundError:
                print("Error: Flag file not found")


