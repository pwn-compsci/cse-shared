import argparse
import random
import string
from jinja2 import Template
import re 
import os
import json

def escape_for_regex(value):
    # Escape only regex special characters
    special_chars = r".*+?^$()[]{}|\\"
    escaped = ''.join(f"\\{char}" if char in special_chars else char for char in value)
    # Double-escape backslashes for JSON compatibility
    return escaped.replace("\\", "\\\\")



# Load positive strings
# Automatically load files from /challenge/randfiles and create variables
randfiles_dir = '/challenge/randfiles'
loaded_data = {}
global_vars_added = []
for filename in os.listdir(randfiles_dir):
    if filename.endswith('.json'):
        var_name = f"json_{os.path.splitext(filename)[0]}"
        with open(os.path.join(randfiles_dir, filename)) as f:
            loaded_data[var_name] = json.load(f)
            global_vars_added.append(var_name)
    if filename.endswith('.txt'):
        var_name = os.path.splitext(filename)[0]
        with open(os.path.join(randfiles_dir, filename)) as f:
            loaded_data[var_name] = [line.strip() for line in f if line.strip()]
            global_vars_added.append(var_name)

# Unpack loaded data into individual variables
globals().update(loaded_data)

# Generate unique variable names
chosen_varnames = random.sample(varnames, 20)

# Generate 10 distinct lowercase characters
chosen_chars = random.sample(string.ascii_lowercase, 20)

# Generate 10 distinct random integers
chosen_ints = random.sample(range(20, 100000), 20)

# Create context dictionary
context = {}

context[f'item_type'] = random.choice(list(json_item_types.keys()))

context['items'] = json_item_types[context[f'item_type']]

# choose the io_type to use this session
context['io_type'] = random.choice(json_io_types)

# choose the io_type to use this session
context['io_subtype'] = random.choice(json_io_subtypes)

for i in range(1, 20):
    context[f'varname{i}'] = chosen_varnames[i - 1]
    context[f'random_character{i}'] = chosen_chars[i - 1]
    context[f'random_integer{i}'] = chosen_ints[i - 1]
    context[f'random_semicolon{i}'] = random.choice("; ;:;.;,")
    context[f'random_double_quote{i}'] = '"'

context['random_comparator'] = random.choice(["<", "<=", ">", ">=", "==", "!="])
context['random_math_symbol'] = random.choice("+-*/=^%")
context['random_paired_value'] = random.randint(1,20)
context['random_paired_value_name'] = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"][context['random_paired_value']]

context['random_ittr_varname'] = random.choice("acitxyz")

context['random_string_size'] = random.choice([200, 250, 300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 950])
context['small_random_string_size'] = random.choice([100, 125, 150, 175, 200, 225, 250, 275])
# Change a single random position in the list of random_double_quote to "'"
random_index = random.randint(1, 6)
context[f'random_double_quote{random_index}'] = "'"

context['operator'] = random.sample(['Add', 'Subtract', 'Multiply'], 3)

# Add 2 random positive strings
context['random_positive_string1'], context['random_positive_string2'] = random.sample(positive_strings, 2)

# Add random menu target, "an item"
# Automatically select a random choice from each loaded global variable
# -1 is to remove the s from the end of the variable name
for var_name in global_vars_added:
    if var_name.startswith('json'):
        continue 
    if isinstance(loaded_data[var_name], list):
        
        if len(loaded_data[var_name]) >= 10:
            values = random.sample(loaded_data[var_name], 10)
            context[var_name[:-1]] = values[0]
            for i in range(1, 10):
                context[f'{var_name[:-1]}{i}'] = values[i]
        else:
            context[var_name[:-1]] = random.choice(loaded_data[var_name])
    else:
        context[var_name[:-1]] = loaded_data[var_name]

context['menu_confirmation_replaced'] = escape_for_regex(context['menu_confirmation']).replace('__', "[0-9]+")

# Add 'menu_target_name' by stripping 'a ' or 'an ' from the start of 'menu_target'
if context['menu_target'].startswith('an '):
    context['menu_target_name'] = context['menu_target'][3:].strip()
elif context['menu_target'].startswith('a '):
    context['menu_target_name'] = context['menu_target'][2:].strip()
else:
    context['menu_target_name'] = context['menu_target'].strip()

context['value_entered_prompt_replaced_num'] = escape_for_regex(context['value_entered_prompt']).replace('__', "[0-9]+")
context['value_entered_prompt_replaced_str'] = escape_for_regex(context['value_entered_prompt']).replace('__', "\\\\w+")

# Parse input files
parser = argparse.ArgumentParser(description="Render one or more Jinja template files in-place.")
parser.add_argument("files", metavar="FILE", nargs="+", help="Template file(s) to render")
args = parser.parse_args()

flag = open("/flag","r").read()

# XOR the flag with the key and ensure the result is printable in a C program string
def xor_encrypt(data, key):
    key = (key * (len(data) // len(key) + 1))[:len(data)]
    encrypted = ''.join(chr(ord(c) ^ ord(k)) for c, k in zip(data, key))
    return ''.join(f"\\x{ord(c):02x}" for c in encrypted)

# Encrypt the flag and store it in the context
context['encrypted_flag'] = xor_encrypt(flag, context['random_positive_string1'])

context['word']  = random.sample(varnames, 70)

# Process each file
for filename in args.files:
    print(f"[pg] Processing: {filename}")
    with open(filename, 'r') as f:
        template = Template(f.read())
        # print("Context keys:", [key for key in context.keys() if 'str' in key])
        rendered = template.render(**context)

    if filename.endswith('.j2'):
        old_filename = filename
        filename = filename[:-3]
        try:
            print("[pg] Removing old file:", old_filename)
            os.remove(old_filename)
        except Exception as e:
            print(f"[pg] Failed to remove {old_filename}: {e}")            
        
    with open(filename, 'w') as f:
        f.write(rendered)

    print(f"[pg] Rendered: {filename}")

