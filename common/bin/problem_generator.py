import argparse
import random
import string
from jinja2 import Template
import re 
import os
import json
import hashlib
import time

import ipaddress
import random
import re
import socket
import fcntl
import struct



def generate_random_ips_in_subnet(subnet, count=3):
    network = ipaddress.IPv4Network(subnet, strict=False)
    all_ips = list(network.hosts())
    exclude_range = [ipaddress.IPv4Address(f"206.206.0.{i}") for i in range(11)]
    valid_ips = [ip for ip in all_ips if ip not in exclude_range]
    random_ips = random.sample(valid_ips, count)
    return [str(ip) for ip in random_ips]




def generate_random_mac():
    # Generate 6 random bytes
    mac_bytes = [random.randint(0, 255) for _ in range(6)]
    # Set first byte: clear multicast bit (LSB), set local admin bit (second LSB)
    mac_bytes[0] = (mac_bytes[0] & 0b11111110) | 0b00000010
    
    # Convert bytes to hexadecimal string format
    mac_string = ':'.join([f'{byte:02x}' for byte in mac_bytes])
    
    return mac_string


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

# create a random password from 4 random varnames ex: orbit_zip_inch_jog
context['random_password'] = "_".join(chosen_varnames[14:18])


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
context['very_small_string_sizes'] = random.choice([16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64])
# Change a single random position in the list of random_double_quote to "'"
random_index = random.randint(1, 6)
context[f'random_double_quote{random_index}'] = "'"

# Add 2 random positive strings
context['random_positive_string1'], context['random_positive_string2'] = random.sample(positive_strings, 2)

# Create a solution file with 10 random positive strings
context['messages'] = random.sample(positive_strings, 10)
context['solution_filename'] = f"/challenge/{chosen_varnames[18]}_{chosen_varnames[19]}.txt"
with open(context['solution_filename'], 'w') as f:
    f.write('\n'.join(context['messages']) + '\n')
print(f"[pg] Created solution file named '{context['solution_filename']}'")

subnet = "206.206.0.0/16"
random_ips = generate_random_ips_in_subnet(subnet, count=10)

rand_net_clients = [{"subnet": subnet,"ip": ip, "mac": generate_random_mac(), "seq": random.randint(0, 2**32 - 1), "sport": random.randint(10000, 60000), "dport": random.randint(10000, 60000)} for ip in random_ips]
context['rand_net_clients'] = rand_net_clients
context['random_port'] = random.randint(10000, 60000)
def get_ip_address(ifname):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8915,  # SIOCGIFADDR
        struct.pack('256s', ifname[:15].encode('utf-8'))
    )[20:24])

try:
    context['known_ip'] = get_ip_address('eth0')
except Exception:
    context['known_ip'] = '127.0.0.1'

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
    menu_target_base = context['menu_target'][3:].strip()
elif context['menu_target'].startswith('a '):
    menu_target_base = context['menu_target'][2:].strip()
else:
    menu_target_base = context['menu_target'].strip()

import re
context['menu_target_name'] = re.sub(r'[^a-zA-Z0-9_]', '_', menu_target_base).strip('_')

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

def md5_hash_flag(flag, randomstr=""):    
    flag_content = flag.encode()  # Ensure the flag is in bytes
    current_time = str(int(time.time())).encode()  # Get current timestamp
    flag_content = current_time + flag_content
    md5_hash = hashlib.md5(flag_content).hexdigest()
    return md5_hash

context['md5_hash_flag'] = md5_hash_flag(flag, context['random_positive_string1'])

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

