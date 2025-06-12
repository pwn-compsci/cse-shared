import argparse
import requests
from bs4 import BeautifulSoup
import re 
import paramiko 
import os 
import traceback 
import time 
import yaml 

BASE_URL = "https://pwn.college"
localhost_dojo="cse240-fa24~1d8d731b"
pwncollege_dojo ="cse240-fa24~67476d68"
dojo_id = pwncollege_dojo
ssh_host = "pc2"

def get_csrf_token(session, url):
    
    response = session.get(url)
    
    csrf_token_match = re.search(r"['\"]csrfNonce['\"]\s*:\s*['\"]([^'\"]+)['\"]", response.text)
    if csrf_token_match:
        csrf_token = csrf_token_match.group(1)
        return csrf_token
    else:
        return None

def login_to_pwn_college(session, csrf_token, username, password):
    login_url = BASE_URL + "/login?next=/"
    
    form_data = {}
    #print(form)
    # Add username, password, and next parameter to the form data
    form_data['name'] = username
    form_data['password'] = password
    form_data['_submit'] = "Submit"
    form_data["nonce"] = csrf_token 

    # Get form action and method
    
    method = "POST"
    
    # Send the request based on the form method
    if method == 'POST':
        response = session.post(login_url, data=form_data)
    else:
        response = session.get(login_url, params=form_data)
    if response.history:
        for resp in response.history:
            #print(f"Redirected from {resp.url} to {response.url} with a {resp.status_code}")
            if (resp.status_code == 302):
                #print(resp.headers)                
                print("Login successful.")
                return True 

    print("Login failed.")
    return False

def make_json_request(session, method, url, data, headers):
    session.headers.update(headers)

    if method.lower() == 'post':
        response = session.post(url, json=data, headers=headers)
    elif method.lower() == 'get':
        response = session.get(url, headers=headers, params=data)
    else:
        raise ValueError("Unsupported HTTP method")
    return response

def open_level(session, csrf_token, dojo, module, challenge):
    

    url = BASE_URL + '/pwncollege_api/v1/docker'
    
    headers = {
        'content-type': 'application/json',
        'csrf-token': csrf_token            
    }
    
    data = {
        "dojo": dojo,
        "module": module,
        "challenge": challenge,
        "practice": False
    }
    
    response = make_json_request(session, 'post', url, data, headers)

    if "true" in response.text:
        return True
    else:
        print("Response from API")
        print("-"*50)
        print(response.text)
        print("-"*50)
        return False 

        

def run_ssh_command(hostname):
    try:
        command = "echo 'End of System for this container'; exit"
        # Create an SSH client
        ssh = paramiko.SSHClient()
        # Automatically add the server's host key (not recommended for production use)
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Load system SSH configuration
        ssh_config = paramiko.SSHConfig()
        with open(os.path.expanduser('~/.ssh/config')) as f:
            ssh_config.parse(f)

        # Get the host configuration
        host_config = ssh_config.lookup(hostname)

        # Extract parameters from the host configuration
        resolved_hostname = host_config['hostname']
        username = host_config.get('user')
        port = int(host_config.get('port', 22))
        key_filename = host_config.get('identityfile', [None])[0]

        ssh.connect(resolved_hostname, username=username, port=port, key_filename=key_filename)
        
        # Create a new channel for interaction
        channel = ssh.invoke_shell()
        
        # Run the command in the interactive shell
        channel.send(f'{command}\n')
        
        # Give the command time to execute
        time.sleep(2)
        
        # Read the command output
        output = ""
        while channel.recv_ready():
            output += channel.recv(65535).decode()

        # Close the channel and connection
        channel.close()
        ssh.close()
        
        if "end of system for this container" in output.lower():
            return True
        
        # Check if "failed" is in the output
        if "Too many failures" in output.lower() :
            print("Failed found in the output")

        if "no active challenge session" in output.lower() :
            print("No active challenge session ")
        
        print("Failed to find expected message")
        print("-"*50)
        print(output)
        print("-"*50)

        return False 

        

    except Exception as e:
        print(f"An error occurred: {e}")
        traceback.print_exc()
        

def main(username, password, module_filter=""):
    
    with open("dojo.yml", "r") as rf:
        dojoinfo = yaml.load(rf, Loader=yaml.SafeLoader)
    
    session = requests.Session()
    csrf_token = get_csrf_token(session, BASE_URL + "/login")
    
    if not login_to_pwn_college(session, csrf_token, username, password):
        print ("Failed the login, try again ")
        exit(19)
    
    csrf_token = get_csrf_token(session, f"{BASE_URL}/{dojo_id}/")        
    print("---- Starting tests ---- ")    

    modules = dojoinfo["modules"]
    for module in modules:
        if len(module_filter) == 0 or module_filter == module['id']:
            print(f"Starting {module['id']}")
            for chal in module["challenges"]:
                print(f"\tTesting {chal['id']}...", end="") 
                if open_level(session, csrf_token, dojo_id,module['id'] , chal['id']):
                    print("Opened Container...", end="")
                else:
                    print("failed to open container")
                    exit(32)
                if run_ssh_command(ssh_host):
                    print(f"Passed {chal['id']}")
                else:
                    print(f"\n\tFailed {module['id']} {chal['id']}")
                    exit(33)
        

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Login to pwn.college and perform actions.")
    parser.add_argument('username', type=str, help="The username for login")
    parser.add_argument('password', type=str, help="The password for login")
    parser.add_argument('--module_filter','--module-filter', type=str, default="", help="The module ID to test otherwise all modules are tested")

    args = parser.parse_args()
    main(args.username, args.password, args.module_filter)
