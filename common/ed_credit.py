#!/usr/bin/exec-suid -- /usr/bin/python3


import base64
import json
import os 
import sys
import traceback 

with open("/challenge/.config/level.json", "r") as rf:
    cdata = json.load(rf)


    
labid = cdata.get('labid', "")
levelid = cdata.get('level', "")


DEBUG = os.getenv("DEBUG") is not None

def unxor_base64_to_string(base64_string):
    # Decode the Base64 string into bytes
    try:
        xor_bytes = base64.b64decode(base64_string)

        print("Sucessfully loaded solution string.")
    except Exception as ex:
        print("Error input did not match expected format, please get help from professor or TA")
        sys.exit(102)
    
    edlesson_ids = []
    with open("/challenge/.config/info.dat", "r") as rf:
        # pwnid, ed lessons id, student id 
        lines = rf.readlines()
        for line in lines:
            if ";" in line:
                students = line.split(",")
                edlesson_ids = [student.split(";")[1] for student in students]
    
    for edlesson_id in edlesson_ids:
        try:
            key = int(edlesson_id)
            # Apply the XOR operation with the key and convert back to characters
            original_chars = [chr((byte ^ key) % 256) for byte in xor_bytes]
            # Combine the characters back into the original string
            original_string = ''.join(original_chars)
            if "," in original_string and edlesson_id in original_string:
                break
        except:
            continue
    else:
        print("Error input did not match expected format, please get help from professor or TA")
        sys.exit(102)
    
    return original_string


def main():
    if len(sys.argv) == 2:
        solution_string = sys.argv[1]
    else:
        # Prompt the user for the solution string
        solution_string = input("Enter your solution string from ed lessons\n > ")

    solution_string = solution_string.strip()
    #{ed lessons id},{level_config['labid']},{level_config['level']}
    result = unxor_base64_to_string(solution_string)
    result_info = result.split(",")
    if DEBUG:
        print(f"result_info: {result_info}")

    if len(result_info) != 3:
        print("Error input did not match expected format, please get help from professor or TA")
        return 102
    
    if result_info[1] == labid and result_info[2] == levelid:
        with open("/flag", "r") as rf:
            print(f"Congrats here's your flag")
            print(rf.read())
    else:
        print("Solution did not contain the solution information, contact professor or a TA")
        print(f"Found labid: {result_info[1]} and levelid: {result_info[2]} expected labid: {labid} and levelid: {levelid}")
        print(f"User information: {result_info}")
        return 105




if __name__ == "__main__":

    main()

