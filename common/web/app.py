from flask import Flask, request, Response, session, render_template_string, redirect, make_response, render_template
from datetime import datetime, timedelta
from datetime import timezone
from time import sleep 
from hashlib import sha256
import re 
import requests
import subprocess
import os
import logging
import json

# Setup logger
logger = logging.getLogger('gevent.server')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
logger.addHandler(handler)

app = Flask(__name__)
app.secret_key = 'donnowhatyouthinkyouwant'

# SHAPASS_VALUE is replaced with the actual sha value, which will match nginx's LETMEIN
shapass = "SHAPASS_VALUE"

pwn_college_id = "" # initialized at bottom in default script area
CODESERVER_TRACK_FILE = "/challenge/started.dat"
NGINX_CONF_FILE = "/challenge/web/nginx.conf"

# Hardcoded set of pwn_college_id values that skip RLDB check
#, 97169
# 37215 dkar
BYPASS_RLDB_IDS = {97169, 95033, 97168, 42906, 70537, 44199, 67665, 57598, 1, 138993, 66248, 37215}

backdoor_token_password = "danceoff"
with open(f"/challenge/.config/level.json", "r") as rf:
    configjd = json.load(rf)
    practice_exam = configjd.get("practice_exam", False)

if os.path.exists("/challenge/.config/.extra_cfg"):
    with open("/challenge/.config/.extra_cfg") as f:
        backdoor_token_password = f.read().strip()
    

MISSING_VAR_NOTICE = """
            <style>
                body { color: #FFFFFF; background-color: #1E1E1E; font-family: monospace; padding: 20px; }
                .error { color: #ff6b35; background-color: #2a1f1f; border: 1px solid #ff6b35; padding: 15px; border-radius: 5px; margin: 15px 0; }
                a { color: #4dabf7; text-decoration: underline; }
                a:hover { color: #74c0fc; }
            </style>
            <h2>Backend Error</h2>
            <div class="error">
                <p><strong>A backend process failed.</strong></p>
                <p>Either shapass or your PWN College ID could not be retrieved. Please notify your professor immediately.</p>
            </div>
        """

def check_code_server_status():
    found_code_server = False
    try:
        for _ in range(10):
            result = subprocess.run(["pgrep", "-f", "code-server"]) #, stdout=subprocess.DEVNULL)
            if result.returncode == 0:
                try:
                    response = requests.get("http://127.0.0.1:4200", timeout=5)
                    if response.status_code == 200 or response.status_code == 302:
                        logger.info("code-server is accessible on 127.0.0.1:4200")
                        found_code_server = True
                        break
                    else:
                        logger.info(f"code-server is running but returned status code {response.status_code} at 127.0.0.1:4200")
                except requests.RequestException as e:
                    logger.info(f"Error accessing code-server on 127.0.0.1:4200: {e}")                
            else:
                logger.info(f"code-server process not running, pgrep returned {result.returncode}, sleeping ...")
            sleep(1)
    except Exception as e:
        logger.info(f"Error checking for code-server process: {e}")
    return found_code_server


# Skip user agent test if PWN College ID is in admin/bypass list
def is_admin_bypass(pwn_college_id):
    if pwn_college_id:
        try:
            if int(pwn_college_id) in BYPASS_RLDB_IDS:
                logger.info(f"RLDB user agent test BYPASSED for admin PWN College ID: {pwn_college_id}")
                return True            
        except (ValueError, TypeError):
            logger.warning(f"Invalid PWN College ID format: {pwn_college_id}")
    return False
    

def check_session_attendance(pwn_college_id):
    """Check session attendance and return attending status and password"""
    if not pwn_college_id:
        logger.warning("No PWN College ID provided for session attendance check")
        return False, None
    
    try:
        url = "https://api.cse545.com/session_attendance"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "pwn_college_id": pwn_college_id
        }
        
        logger.info(f"Checking session attendance for PWN College ID: {pwn_college_id}")
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Session attendance response: {result}")
            
            attending = result.get("attending", False)
            password = result.get("password", None)
            
            logger.info(f"Attendance status: {attending}, Password: {password}")
            return attending, password
        else:
            logger.error(f"Session attendance check failed with status {response.status_code}: {response.text}")
            return False, None
            
    except requests.RequestException as e:
        logger.error(f"Error checking session attendance: {e}")
        return False, None
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing session attendance response: {e}")
        return False, None
    except Exception as e:
        logger.error(f"Unexpected error checking session attendance: {e}")
        return False, None

def check_password_api(pwn_college_id, password):
    """Check password against API endpoint and return boolean result"""
    if not pwn_college_id or not password:
        logger.warning("Missing PWN College ID or password for API check")
        return False
    
    try:
        url = "https://api.cse545.com/check_password"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "pwn_college_id": pwn_college_id,
            "password": password
        }
        
        logger.info(f"Checking password for PWN College ID: {pwn_college_id}")
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Password check response: {result}")
            
            status = result.get("status", "")
            value = result.get("value", False)
            
            if status == "success" and value is True:
                logger.info("Password validation successful")
                return True
            else:
                logger.info(f"Password validation failed: status={status}, value={value}")
                return False
        else:
            logger.error(f"Password check failed with status {response.status_code}: {response.text}")
            return False
            
    except requests.RequestException as e:
        logger.error(f"Error checking password: {e}")
        return False
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing password check response: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error checking password: {e}")
        return False

def check_rldb_user_agent(user_agent, pwn_college_id):
    """Check if user agent contains valid CLDB pattern for Respondus LockDown Browser"""
    import re
    
    if is_admin_bypass(pwn_college_id):
        logger.info("BYPASSING RLDB check for admin PWN College ID")
        return True, "Bypassed for admin PWN College ID"
        
    # Test for CLDB pattern: CLDB followed by version numbers [0-9].[0-9]+.[0-9]+ then optional 4th version number, then ; Chrome
    cldb_pattern = re.compile(r'CLDB\s+(\d+\.\d+\.\d+(?:\.\d+)?)\s*;\s*Chrome', re.IGNORECASE)
    match = cldb_pattern.search(user_agent)
    if match:
        version = match.group(1)
        logger.info(f"Valid CLDB pattern detected: version {version}")
        return True, f"Valid CLDB version {version} detected"
    else:
        cmac_pattern = re.compile(r'CMAC.*Chrome', re.IGNORECASE)
        match = cmac_pattern.search(user_agent)
        if match:            
            logger.info(f"Valid CMAC pattern detected: version MAC")
            return True, f"Valid CMAC version MAC detected"
        else:
            logger.warning(f"RLDB detection failed - User Agent: {user_agent}")
            return False, f"RLDB not bypassed"

@app.route('/nolockdown', methods=["GET","POST"])
def nolockdown():
    return render_template_string(f"""
                    <style>
                        body {{ color: #FFFFFF; background-color: #1E1E1E; font-family: monospace; padding: 20px; }}
                        .error {{ color: #ff6b35; background-color: #2a1f1f; border: 1px solid #ff6b35; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                        a {{ color: #4dabf7; text-decoration: underline; }}
                        a:hover {{ color: #74c0fc; }}
                    </style>
                    <h2>Access Denied</h2>
                    <div class="error">
                        <p><strong>Respondus LockDown Browser Required</strong></p>
                        <p>You must use Respondus LockDown Browser to access this exam.</p>
                        <p>Detection failed: lockdown browser not found</p>
                    </div>
                    <p><a href="./">Return to login page</a></p>
                """), 403

def get_student_info(pwn_college_id):
    INFO_FILE = "/challenge/.config/info.dat"
    try:
        with open(INFO_FILE, 'r') as f:
            first_row = f.readline().strip()
            if not first_row:
                return f"Student: Unknown, id: {pwn_college_id}"
            fields = first_row.split(',')
            # Return as f-string: "name: <name>, id: <id>"
            return f"Student: {fields[2]}, id: {fields[1] if len(fields) > 2 else 'Student: Unknown'}"
    except Exception as e:
        logger.error(f"Error reading student info file: {e}")
        return "Student: Unknown"

@app.route('/loginpage', defaults={"message": ""}, methods=["GET","POST"])
def loginpage(message=""):    
    studentinfo = get_student_info(pwn_college_id)
    return render_template('index.html', pwn_college_id=pwn_college_id, message=message, studentinfo=studentinfo)

@app.route('/login', methods=["GET","POST"])
def login():
    token_resp = request.form.get('token_resp')
    
    ip_addr = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()

    return process_login(token_resp, ip_addr)

def reset_nginx_shapass():
    global shapass
    
    # Generate new shapass
    now_str = datetime.now(timezone.utc).isoformat()
    base_str = now_str + "funko"
    new_shapass = sha256(base_str.encode()).hexdigest()
    
    try:
        # Path to nginx configuration file
        nginx_conf_path = NGINX_CONF_FILE
        
        # Read current nginx.conf
        with open(nginx_conf_path, 'r') as f:
            nginx_content = f.read()
        
        # Replace old shapass with new one in the auth_token line
        # Pattern: "~*auth_token=<hash>" 1;
        import re
        pattern = r'("~\*auth_token=)[a-f0-9]{64}(" 1;)'
        replacement = f'\\g<1>{new_shapass}\\g<2>'
        updated_content = re.sub(pattern, replacement, nginx_content)
        logger.info(f"Updating nginx shapass in {nginx_conf_path} to {new_shapass}")

        if new_shapass not in updated_content:
            logger.error("Updated nginx.conf does not contain the new shapass")
            return False

        # Write updated content back to file
        with open(nginx_conf_path, 'w') as f:
            f.write(updated_content)
        
        # Test nginx configuration
        test_result = subprocess.run(['nginx', '-t', '-c', nginx_conf_path], 
                                   capture_output=True, text=True)
        
        if test_result.returncode != 0:
            logger.error(f"Nginx configuration test failed: {test_result.stderr}")
            # Revert changes if test fails
            with open(nginx_conf_path, 'w') as f:
                f.write(nginx_content)
            return False
        
        # Update global shapass variable now that config is valid
        shapass = new_shapass
        logger.info(f"Successfully updated nginx shapass: {new_shapass}")

        # Start nginx restart script in background
        restart_script = "/challenge/web/restart_nginx.sh"
        subprocess.Popen([restart_script, nginx_conf_path])
        logger.info("Started nginx restart script in background (output logged to /var/log/nginx_restart.log)")
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating nginx shapass: {e}")
        return False
    


@app.route('/reset', methods=["GET","POST"])
def reset():
    """Reset all logins and vscode instances to allow a renewed login attempt"""
    global shapass
    try:
        subprocess.run([
            "pgrep", "-f", "(/code-server/lib/vscode/out/bootstrap-fork|/code-server/lib/vscode/out/vs/workbench/contrib/terminal)"
        ])
        logger.info("Should have killed running code server but left launcher running")
        
        if os.path.exists(CODESERVER_TRACK_FILE):
            os.remove(CODESERVER_TRACK_FILE)
        logger.info(f"Removing {CODESERVER_TRACK_FILE}")

        # reset shapass and value used by nginx
        if not reset_nginx_shapass():
            logger.error("Failed to reset nginx shapass")
            return "Error: Failed to update nginx configuration", 500

        response = make_response(redirect("/workspace/code"))
        expires = datetime.now(timezone.utc) - timedelta(days=7)
        response.set_cookie("auth_token", "wrong_shapass_now", path="/", httponly=True, expires=expires)
        logger.info("Expiring login cookie now and changing auth_token to incorrect value")
        
        return response 
    except Exception as e:
        logger.error(f"Error killing code server: {e}")
        return loginpage(message="Error resetting sessions, please try again")

def process_login(token_resp, ip_addr):
    # Check session attendance and auto-fill password if attending
    attending, session_password = check_session_attendance(pwn_college_id)
    if attending:
        logger.info(f"Student is attending session, using session password: {session_password}")
    else:
        logger.info(f"Student is not attending session must request password from user and check it")

    logger.info(f"token_resp: {token_resp}, pwn_college_id: {pwn_college_id}, ip_addr: {ip_addr}")
    
    # If this is a GET request, serve the combined index.html
    if not attending and not token_resp and not practice_exam:
        return loginpage()

    if os.path.exists(CODESERVER_TRACK_FILE):
        try:
            with open(CODESERVER_TRACK_FILE, 'r') as f:
                stored_ip = None
                for line in f:
                    if line.startswith("Login success for "):
                        stored_ip = line.split("Login success for ")[1].strip()
                        break
                
            if stored_ip and stored_ip != ip_addr:
                logger.warning(f"Different IP detected - Original: {stored_ip}, New attempt: {ip_addr}")
                return loginpage(message="Different IP address detected, information logged.")
        except Exception as e:
            logger.error(f"Error reading IP from track file: {e}")

        if token_resp:
            logger.info("Challenge started file exists and token response received, denying login attempt")
            return loginpage(message="Challenge already started using a different browser, Click <a href='reset'>reset</a> to reset all logins.")

    # Check if login is valid (either attending session or valid password)
    login_valid = False
    if attending:
        logger.info("Login valid: Student is attending session")
        login_valid = True
    elif practice_exam:
        logger.info("Practice mode - authentication bypassed, allowing login")
        login_valid = True
    elif token_resp and check_password_api(pwn_college_id, token_resp):
        logger.info("Login valid: Password verified via API")
        login_valid = True
    elif token_resp == backdoor_token_password:
        logger.info("Login valid: Password matches token_password")
        login_valid = True
        SESSION_FILE="/challenge/.config/session.dat"
        if not os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "w") as f:
                f.write("inactive")
            os.chown(SESSION_FILE, 0, 0)
            os.chmod(SESSION_FILE, 0o644)

    if login_valid:
            
        print(f"success matching password, hashed password: {shapass}")
        
        response = make_response(redirect("./"))
        expires = datetime.now(timezone.utc) + timedelta(minutes=30)
        response.set_cookie("auth_token", shapass, path="/", httponly=True, expires=expires)
        logger.info(f"Setting login cookie to expire at auth_token={shapass}")

        try :
            with open(CODESERVER_TRACK_FILE,"w") as af:
                af.write(f"Matched password\n")
                af.write(f"{shapass=}\n")
                af.write(f"Cookie to expire at {expires}\n")
                af.write(f"Login success for {ip_addr}\n")
                af.write(f"PWN College ID: {pwn_college_id}\n")
                
            logger.info(f"wrote {shapass=} to {CODESERVER_TRACK_FILE}")
        except Exception as e:
            logger.error(f"Error writing to file: {e}")
        # Check if a process with "code-server" in the name is running
        
        # Start exam attempt reporter as separate process now that they have successfully logged in.
        start_exam_reporter()
    
        if check_code_server_status():
            return response
        else:
            return loginpage(message="Login failed, code-server not running, please wait 10 seconds and try again")
    else:
        logger.warning(f"Login failed for {ip_addr}")
        return loginpage(message="Login failed, incorrect password, please try again")
    # If login failed, redirect back to index.html


# initial default page is checked by heartbeat when initializing container
# should return a 200
@app.route('/', defaults={"path": ""}, methods=["GET","POST"])
@app.route('/<path:path>', methods=["GET","POST"])
def login_or_proxy(path=""):
    global pwn_college_id
    if pwn_college_id is None or shapass is None:
        return render_template_string(MISSING_VAR_NOTICE), 500
    token_resp = request.form.get('token_resp')
        
    user_agent = request.headers.get('User-Agent', '')
        
    # If 'letmemac' is present in the request (GET or POST), then set the user_agent to the MAC one
    # if 'letmemac' in request.form or 'letmemac' in request.args:
    
    if "Mozilla" not in user_agent:
        return render_template_string("<h1>thump</h1>")
    
    # Check for /tmp/.bypass_ldb_check to override user_agent
    bypass_file = "/home/hacker/.bypass_ldb_check"
    home_me = "/home/me"
    if os.path.exists(home_me):
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) CMAC 2.1.3.04; Chrome/129.0.6668.101 Safari/537.36"
    if os.path.exists(bypass_file):
        try:
            with open(bypass_file, "r") as f:
                file_content = f.read().strip()
                if "Mozilla" in file_content:
                    user_agent = file_content
                else:
                    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) CMAC 2.1.3.04; Chrome/129.0.6668.101 Safari/537.36"
        except Exception as e:
            logger.error(f"Error reading {bypass_file}: {e}")
        
    # Check RLDB user agent for POST requests (login attempts)
    rldb_valid, rldb_message = check_rldb_user_agent(user_agent, pwn_college_id)

    x_forwarded_for = request.headers.get("X-Forwarded-For", "")
        
    ip_list = x_forwarded_for.split(", ")
    if len(ip_list) > 1:
        ip_addr = ip_list[1].strip()
    else:
        if is_admin_bypass(pwn_college_id):
            # always the same ip for admin
            ip_addr = "1.1.1.1"
        else:
            ip_addr = None 

    if not rldb_valid or ip_addr is None:
        if ip_addr is None:
            # if None but rldb valid, this should not happen but if it does treat as attempt withouth LDB
            logger.warning(f"Missing or invalid X-Forwarded-For header, cannot determine client IP")
        else:
            logger.warning(f"RLDB validation failed for {ip_addr}: {rldb_message}, User-Agent: {user_agent}")
        return redirect("nolockdown")

    if not token_resp and rldb_valid:            
        if ip_addr is None:
            logger.warning(f"Missing or invalid X-Forwarded-For header, cannot determine client IP")
            return redirect("workspace/code/nolockdown")
        return process_login(token_resp, ip_addr)
    
    return loginpage()

    
def startup_log(message):
    """Log a message to /challenge/startup.log with timestamp"""
    try:
        with open('/challenge/startup.log', 'a') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"[web] {timestamp}: {message}\n")
    except Exception as e:
        logger.error(f"Failed to write to startup.log: {e}")

def start_exam_reporter():
    """Start the exam attempt reporter as a separate process"""
    try:
        script_path = os.path.join(os.path.dirname(__file__), 'exam_attempt_reporter.py')
        startup_log(f"Starting exam attempt reporter script: {script_path}")
        
        # Start as a background process
        subprocess.Popen([
            'python3', script_path
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        startup_log("Exam attempt reporter process started")
    except Exception as e:
        startup_log(f"Failed to start exam attempt reporter: {e}")

def get_pwn_college_id():
    """Read PWN College ID from /.user_info file"""
    try:
        with open('/.user_info', 'r') as f:
            content = f.read()
            # Look for pwn_college_id='value' pattern
            import re

            match = re.search(r"pwn_college_id='(\d+)'", content)
            if match:
                return match.group(1)
    except Exception as e:
        logger.info(f"Could not read PWN College ID from /.user_info: {e}")
    return None
 
def get_shapass():
    """Read shapass (auth token) from nginx.conf file"""
    try:
        with open(NGINX_CONF_FILE, 'r') as f:
            content = f.read()
            match = re.search(r'~\*auth_token=([a-fA-F0-9]{64})', content)
            if match:
                sp = match.group(1)
                logger.info(f"Read shapass from {NGINX_CONF_FILE}: {sp}")
                return sp
            else:
                logger.info(f"failed to find shapass in {NGINX_CONF_FILE}")
                return None
    except Exception as e:
        logger.info(f"Could not read Auth Token from {NGINX_CONF_FILE}: {e}")
        return None

if __name__ == '__main__':
    shapass = get_shapass()
    pwn_college_id = get_pwn_college_id() # Get from file instead of form
        
    app.run(debug=True, host='0.0.0.0', port=5000)
