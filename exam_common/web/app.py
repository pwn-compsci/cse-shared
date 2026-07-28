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
FLAG_EXEMPTED_PATH = "/flag_exempted"

# Exam administration type configuration
exam_admin_type = "Proctoring plus Lockdown Browser"  # Default to most restrictive
exam_module = ""
exam_challenge = ""
EXAM_ADMIN_API_TOKEN = "08b26e01b8d9cb4f262da37836912504104296c33ab658dca836d032bc47b2ff"
EXAM_ADMIN_API_URL = "https://api.cse545.com/exam_admin_type"

# Hardcoded set of pwn_college_id values that skip RLDB check
#, 97169 
# 68880 is Weiyu admin account
# 42906 is Derek admin account
# 97168 Erik 1 
# 129911 Vishal
# 64397 sri
# 109275 madu
# 68429 vmamshi
# 44674 gio
# 157464 omy1 
BYPASS_RLDB_IDS = {95033, 42906, 70537, 44199, 67665, 57598, 68880, 13475, 97168, 129911, 78896, 64397, 109275, 68429, 44674, 157464 }

backdoor_token_password = "sunny"

# Check if this is a practice exam
is_practice_exam = False
LEVEL_CONFIG_PATH = "/challenge/.config/level.json"
try:
    if os.path.exists(LEVEL_CONFIG_PATH):
        with open(LEVEL_CONFIG_PATH, 'r') as f:
            level_config = json.load(f)
            is_practice_exam = level_config.get("is_practice_exam", False)
            if is_practice_exam:
                logger.info("Practice exam detected - password requirement will be bypassed")
except Exception as e:
    logger.error(f"Error reading level config from {LEVEL_CONFIG_PATH}: {e}")

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

def get_exam_admin_type(pwn_college_id, module, challenge):
    """Get exam administration type from API endpoint"""
    if not pwn_college_id or not module or not challenge:
        logger.warning("Missing required parameters for exam admin type check, using default")
        return "Proctoring plus Lockdown Browser"
    
    try:
        payload = {
            "api_token": EXAM_ADMIN_API_TOKEN,
            "pwn_college_id": int(pwn_college_id),
            "module": module,
            "challenge": challenge
        }
        
        logger.info(f"Requesting exam admin type for PWN ID {pwn_college_id}, {module}/{challenge}, {EXAM_ADMIN_API_URL}, {payload}")
        response = requests.post(EXAM_ADMIN_API_URL, json=payload, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            admin_type = result.get("exam_administration_type", "Proctoring plus Lockdown Browser")
            logger.info(f"Exam administration type: {admin_type}")
            return admin_type
        else:
            logger.error(f"Exam admin type API returned status {response.status_code}: {response.text}")
            return "Proctoring plus Lockdown Browser"
            
    except requests.RequestException as e:
        logger.error(f"Error calling exam admin type API: {e}")
        return "Proctoring plus Lockdown Browser"
    except Exception as e:
        logger.error(f"Unexpected error getting exam admin type: {e}")
        return "Proctoring plus Lockdown Browser"

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

def check_session_attendance(pwn_college_id):
    """Check session attendance and return attending status and password
    
    Returns:
        None: No session exists (404 error)
        (False, password): Session exists but not attending yet
        (True, password): Currently attending session
    """
    if not pwn_college_id:
        logger.warning("No PWN College ID provided for session attendance check")
        return None
    
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
        
        # 404 means no session exists at all
        if response.status_code == 404:
            logger.warning(f"No proctor session found (404): {response.text}")
            return None
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Session attendance response: {result}")
            
            # Check valid_session field to determine if a proctor session exists
            valid_session = result.get("valid_session", False)
            if not valid_session:
                logger.warning(f"No valid proctor session found: {result.get('message', 'Unknown reason')}")
                return None
            
            attending = result.get("attending", False)
            password = result.get("password", None)
            
            logger.info(f"Valid session found - Attendance status: {attending}, Password: {password}")
            return attending, password
        else:
            logger.error(f"Session attendance check failed with status {response.status_code}: {response.text}")
            return None
            
    except requests.RequestException as e:
        logger.error(f"Error checking session attendance: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing session attendance response: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error checking session attendance: {e}")
        return None

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

def check_rldb_user_agent(user_agent, pwn_college_id, sec_ch_ua_platform):
    """Check if user agent contains valid CLDB pattern for Respondus LockDown Browser"""
    import re
    
    # Skip RLDB check based on exam administration type
    if exam_admin_type in ["Proctoring", "Proctoring with no attendance", "Honor Lock", "None", ""]:
        logger.info(f"RLDB user agent test BYPASSED - exam type is '{exam_admin_type}'")
        return True, f"Bypassed for exam type: {exam_admin_type}"
    
    # Skip RLDB check for practice exams
    if is_practice_exam:
        logger.info("RLDB user agent test BYPASSED for practice exam")
        return True, "Bypassed for practice exam"
    
    # Skip user agent test if PWN College ID is in admin/bypass list
    if pwn_college_id:
        try:
            if int(pwn_college_id) in BYPASS_RLDB_IDS:
                logger.info(f"RLDB user agent test BYPASSED for admin PWN College ID: {pwn_college_id}")
                return True, "Bypassed for admin PWN College ID"
        except (ValueError, TypeError):
            logger.warning(f"Invalid PWN College ID format: {pwn_college_id}")
    
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
            # Check for Chromebook: sec_ch_ua_platform == "Chrome OS" and user agent contains "CrOS" followed by "Chrome"
            platform_value = sec_ch_ua_platform.strip('"').strip("'")
            if platform_value and platform_value == "Chrome OS":
                cros_pattern = re.compile(r'CrOS.*Chrome', re.IGNORECASE)
                cros_match = cros_pattern.search(user_agent)
                if cros_match:
                    logger.info(f"Valid Chromebook pattern detected: Platform={platform_value}")
                    return True, f"Valid Chromebook detected"
            
            logger.warning(f"RLDB detection failed - User Agent: {user_agent}")
            return False, f"Expected CLDB [version] ; Chrome pattern not found in user agent"

@app.route('/nolockdown', methods=["GET","POST"])
def nolockdown():
    exempted_message = ""
    flag_exempted_path = "/flag_exempted"
    if os.path.exists(flag_exempted_path):
        try:
            with open(flag_exempted_path, "r") as f:
                exempted_message = f"<div class='exemption'><strong>Exemption Notice:</strong><br>Flag is provided to by an exemption for prior work<br>{f.read().strip()}</div>"
        except Exception as e:
            logger.error(f"Error reading {flag_exempted_path}: {e}")

    # Customize message based on exam administration type
    exam_type_display = exam_admin_type if exam_admin_type else "Proctoring plus Lockdown Browser"
    
    return render_template_string(f"""
        <style>
            body {{ color: #FFFFFF; background-color: #1E1E1E; font-family: monospace; padding: 20px; }}
            .error {{ color: #ff6b35; background-color: #2a1f1f; border: 1px solid #ff6b35; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .exemption {{ color: #1e7e34; background-color: #e6ffe6; border: 1px solid #1e7e34; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .info {{ color: #17a2b8; background-color: #1f2a2e; border: 1px solid #17a2b8; padding: 10px; border-radius: 5px; margin: 10px 0; font-size: 0.9em; }}
            a {{ color: #4dabf7; text-decoration: underline; }}
            a:hover {{ color: #74c0fc; }}
        </style>
        <h2>Access Denied</h2>
        <div class="error">
            <p><strong>Respondus LockDown Browser Required</strong></p>
            <p>You must use Respondus LockDown Browser to access this exam.</p>
            <p>Detection failed: lockdown browser not found</p>
        </div>
        <div class="info">
            <p><strong>Exam Type:</strong> {exam_type_display}</p>
        </div>
        {exempted_message}
        <p><a href="">Return to login page</a></p>
    """), 403

def showflag():
    """Display the flag when exemption exists"""
    flag_content = ""
    try:
        with open(FLAG_EXEMPTED_PATH, "r") as f:
            flag_content = f.read().strip()
    except Exception as e:
        logger.error(f"Error reading flag from {FLAG_EXEMPTED_PATH}: {e}")
        flag_content = "Error reading flag file"

    return render_template_string(f"""
        <style>
            body {{ color: #FFFFFF; background-color: #1E1E1E; font-family: monospace; padding: 20px; }}
            .flag {{ color: #28a745; background-color: #1f2f1f; border: 2px solid #28a745; padding: 20px; border-radius: 8px; margin: 20px 0; text-align: center; }}
            .flag h3 {{ margin-top: 0; color: #40c057; }}
            .flag-content {{ font-size: 1.2em; font-weight: bold; background-color: #2d2d2d; padding: 15px; border-radius: 5px; margin: 15px 0; word-break: break-all; }}
            .info {{ color: #17a2b8; background-color: #1f2a2e; border: 1px solid #17a2b8; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            a {{ color: #4dabf7; text-decoration: underline; }}
            a:hover {{ color: #74c0fc; }}
        </style>
        <h2>Flag Exemption</h2>
        <div class="flag">
            <h3>🏆 Congratulations! 🏆</h3>
            <p>You have been granted an exemption for this exam based on prior work.</p>
            <div class="flag-content">{flag_content}</div>
        </div>
        <div class="info">
            <p><strong>Note:</strong> This exemption has been granted due to previous coursework or achievements. However, you must submit the flag below to get credit for completing this exam problem.</p>
        </div>
        <p><a href="">Return to main page</a></p>
    """)
    
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
    exam_password = request.form.get('exam_password')
    
    ip_addr = request.remote_addr

    return process_login(exam_password, ip_addr)

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

@app.route('/status', methods=["GET","POST"])
@app.route('/exam_api/status', methods=["GET", "POST"])
def exam_api_status():
    """Return status information about the exam environment"""
    try:
        status_data = {
            "pwn_college_id": pwn_college_id,
            "code_server_running": check_code_server_status(),
            "started_file_exists": os.path.exists(CODESERVER_TRACK_FILE),
            "flag_exempted": os.path.exists(FLAG_EXEMPTED_PATH),
            "nginx_conf_exists": os.path.exists(NGINX_CONF_FILE),
            "exam_administration_type": exam_admin_type,
            "exam_module": exam_module,
            "exam_challenge": exam_challenge
        }
        
        # Check if attending session (only if proctoring is required)
        if is_practice_exam:
            status_data["attending_session"] = "N/A - practice exam"
        elif exam_admin_type in ["Proctoring plus Lockdown Browser", "Proctoring"]:
            session_result = check_session_attendance(pwn_college_id)
            if session_result is None:
                status_data["attending_session"] = "No session found"
            else:
                attending, _ = session_result
                status_data["attending_session"] = attending
        else:
            status_data["attending_session"] = "N/A - proctoring not required"
        
        return status_data, 200
    except Exception as e:
        logger.error(f"Error in status endpoint: {e}")
        return {"error": str(e)}, 500

@app.route('/killme', methods=["GET","POST"])
@app.route('/exam_api/killme', methods=["GET","POST"])
def killme():
    """Kill process 1 (init/systemd)"""
    try:
        logger.info("Received request to kill process 1, sending SIGKILL")
        # Try multiple approaches to ensure container dies
        subprocess.Popen(['sh', '-c', 'kill -9 1; killall -9 python3; kill -9 -1'], 
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Sent SIGKILL to process 1", 200
    except Exception as e:
        logger.error(f"Error killing process 1: {e}")
        return f"Error: {e}", 500


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

        response = make_response(redirect(""))
        expires = datetime.now(timezone.utc) - timedelta(days=7)
        response.set_cookie("auth_token", "wrong_shapass_now", path="/", httponly=True, expires=expires)
        logger.info("Expiring login cookie now and changing auth_token to incorrect value")
        
        return response 
    except Exception as e:
        logger.error(f"Error killing code server: {e}")
        return loginpage(message="Error resetting sessions, please try again")

# def extract_backup_files():
#     """Extract encrypted backup files to the challenge level directory"""
#     try:
#         # Read level.json to get the target directory
#         with open('/challenge/.config/level.json', 'r') as f:
#             level_data = json.load(f)
#             clevel_work_dir = f"{level_data['hwdir']}/{level_data['level']}"
        
#         logger.info(f"Extracting backup to: {clevel_work_dir}")
        
#         # Check for the encrypted backup file
#         encrypted_filepath = '/tmp/encrypted_clevel_work.tar.gz.enc'
#         if not os.path.exists(encrypted_filepath):
#             logger.warning(f"Encrypted backup file not found: {encrypted_filepath}")
#             return
        
#         logger.info(f"Found backup file: {encrypted_filepath}")
        
#         # Decrypt and extract in one command
#         # Check if helper file exists
#         helper_file = '/.helper'
#         if not os.path.exists(helper_file):
#             logger.warning(f"Helper file not found: {helper_file}")
#             return
        
#         if not os.path.exists(encrypted_filepath):
#             logger.warning(f"Encrypted backup file not found: {encrypted_filepath}")
#             return
        
#         # Read password from helper file
#         try:
#             with open(helper_file, 'r') as f:
#                 password = f.read().strip()
#         except Exception as e:
#             logger.error(f"Error reading password from {helper_file}: {e}")
#             return
        
#         decrypt_cmd = ['openssl', 'enc', '-aes-256-cbc', '-d', '-pbkdf2', '-pass', f'pass:{password}', '-in', encrypted_filepath]
#         extract_cmd = ['tar', '-xzf', '-', '-C', clevel_work_dir]
        
#         # Create the target directory if it doesn't exist
#         os.makedirs(clevel_work_dir, exist_ok=True)
        
#         # Run decrypt | extract pipeline
#         decrypt_process = subprocess.Popen(decrypt_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#         extract_process = subprocess.Popen(extract_cmd, stdin=decrypt_process.stdout, stderr=subprocess.PIPE)
#         decrypt_process.stdout.close()
        
#         # Wait for completion
#         extract_process.communicate()
        
#         if extract_process.returncode == 0:
#             logger.info(f"Successfully extracted backup to {clevel_work_dir}")
#         else:
#             logger.error(f"Failed to extract backup, return code: {extract_process.returncode}")
            
#     except Exception as e:
#         logger.error(f"Error extracting backup files: {e}")


def process_login(exam_password, ip_addr):
    
    logger.info(f"=== process_login called === exam_admin_type: '{exam_admin_type}', exam_password: {exam_password is not None}, is_practice_exam: {is_practice_exam}, pwn_college_id: {pwn_college_id}")
    
    # Check if this is an admin/bypass user (convert to int for comparison)
    try:
        is_admin = int(pwn_college_id) in BYPASS_RLDB_IDS if pwn_college_id else False
    except (ValueError, TypeError):
        is_admin = False
    if is_admin:
        logger.info(f"Admin user detected (PWN ID {pwn_college_id}) - bypassing all authentication requirements")
    
    if is_practice_exam:
        logger.info("Practice exam detected - bypassing all authentication requirements")
    protections_bypassed = is_admin or is_practice_exam
    # Check session attendance based on exam administration type
    attending = False
    session_password = None
    
    # Check session attendance for types requiring proctoring WITH monitoring (skip for admins)
    if not protections_bypassed and exam_admin_type in ["Proctoring plus Lockdown Browser", "Proctoring"]:
        session_result = check_session_attendance(pwn_college_id)
        if session_result is None:
            # No proctor session exists - block login
            logger.error(f"No active proctor session found for exam type '{exam_admin_type}'")
            return loginpage(message="No active proctor session found. Exams with proctoring require an active session.")
        attending, session_password = session_result
        if attending:
            logger.info(f"Student is attending session, using session password: {session_password}")
        else:
            logger.info(f"Student is not attending session yet - will require password")
    # For "Proctoring with no attendance", verify proctor session exists but don't monitor ongoing (skip for admins)
    elif not protections_bypassed and exam_admin_type == "Proctoring with no attendance":
        session_result = check_session_attendance(pwn_college_id)
        if session_result is None:
            logger.warning(f"No active proctor session found for 'Proctoring with no attendance' type")
            return loginpage(message="No active proctor session found. Please ensure a proctor session is scheduled.")
        logger.info(f"Proctor session validated for 'Proctoring with no attendance' - allowing login with password")
    else:
        logger.info(f"Session attendance check SKIPPED - exam type is '{exam_admin_type}' or admin/practice bypass")

    logger.info(f"exam_password: {exam_password}, pwn_college_id: {pwn_college_id}, ip_addr: {ip_addr}")
    
    # Check if password is needed based on exam type
    # Only proctoring types with attendance monitoring and LDB require password (admins bypass this)
    password_required = not protections_bypassed and exam_admin_type in ["Proctoring plus Lockdown Browser", "Proctoring", "Lock Down Browser"]
    logger.info(f"=== Password check === password_required: {password_required}, exam_admin_type: '{exam_admin_type}', is_admin: {is_admin}, is_practice_exam: {is_practice_exam}")
    
    # If this is a GET request and not practice exam or attending or password not required, serve the login page
    if not is_practice_exam and not attending and password_required and not exam_password:
        logger.info("=== Showing loginpage === because password required and not provided")
        return loginpage()
    
    # If password not required but this is a GET (no form submission), allow direct access
    if not password_required and not exam_password and not is_practice_exam:
        logger.info(f"Exam type '{exam_admin_type}' does not require password - allowing direct access")
        # Continue to login validation with login_valid set below

    if not protections_bypassed and os.path.exists(CODESERVER_TRACK_FILE) and exam_password:
        logger.info("Challenge started file exists and token response received, denying login attempt")
        # TODO: add multiple login attempts detected log request to api
        return loginpage(message="Challenge already started using a different browser, Click <a href='reset'>reset</a> to reset all logins.")

    # Check if login is valid (either attending session or valid password)
    login_valid = False
    if is_admin:
        logger.info(f"Login valid: Admin user (PWN ID {pwn_college_id})")
        login_valid = True
    elif is_practice_exam:
        logger.info("Login valid: Practice exam mode - password bypassed")
        login_valid = True
    elif not password_required:
        logger.info(f"Login valid: Exam type '{exam_admin_type}' does not require password")
        login_valid = True
    elif attending:
        logger.info("Login valid: Student is attending session")
        login_valid = True
    elif exam_password and check_password_api(pwn_college_id, exam_password):
        logger.info("Login valid: Password verified via API")
        login_valid = True
    elif exam_password == backdoor_token_password:
        logger.info("Login valid: Password matches token_password")
        login_valid = True

    if login_valid:
            
        print(f"success matching password, hashed password: {shapass}")
        
        # Create or update session.dat based on exam admin type
        # This ensures the session status warning doesn't appear incorrectly
        SESSION_FILE = "/challenge/.config/session.dat"
        try:
            if not os.path.exists(SESSION_FILE):
                # Determine session status based on admin status and exam admin type
                if protections_bypassed:
                    # Admins and practice exams get immediate active status
                    session_status = "active"
                    logger.info("Protections bypassed - session.dat set to active")
                elif exam_admin_type in ["Proctoring plus Lockdown Browser", "Proctoring"]:
                    # These types require attendance monitoring via session_monitor.py
                    # Set to inactive initially - session_monitor will update to active when attending
                    session_status = "inactive"
                    logger.info(f"Exam type '{exam_admin_type}' requires attendance - session.dat set to inactive")
                else:
                    # No attendance monitoring needed - set to active immediately
                    session_status = "active"
                    logger.info(f"Exam type '{exam_admin_type}' does not require attendance - session.dat set to active")
                
                with open(SESSION_FILE, "w") as f:
                    f.write(session_status)
                os.chown(SESSION_FILE, 0, 0)
                os.chmod(SESSION_FILE, 0o644)
                logger.info(f"Created {SESSION_FILE} with status: {session_status}")
        except Exception as e:
            logger.error(f"Error creating session.dat: {e}")
        
        # extract_backup_files()
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
@app.route('/', methods=["GET","POST"])
def login_or_proxy():
    global pwn_college_id
    if pwn_college_id is None or shapass is None:
        return render_template_string(MISSING_VAR_NOTICE), 500
    if os.path.exists(FLAG_EXEMPTED_PATH):
        return showflag()
    exam_password = request.form.get('exam_password')
    
    ip_addr = request.remote_addr
    user_agent = request.headers.get('User-Agent', '')
    sec_ch_ua_platform = request.headers.get('Sec-Ch-Ua-Platform', '')
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
        #  User-Agent: Mozilla/5.0 (X11; CrOS x86_64 14541.0.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36
        
    # Check RLDB user agent for POST requests (login attempts)
    rldb_valid, rldb_message = check_rldb_user_agent(user_agent, pwn_college_id, sec_ch_ua_platform)


    if not rldb_valid:
        logger.warning(f"RLDB validation failed for {ip_addr}: {rldb_message}, User-Agent: {user_agent}")
        return redirect("nolockdown")

    if not exam_password and rldb_valid:
        return process_login(exam_password, ip_addr)

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
    
    # Load exam module and challenge from level.json
    try:
        if os.path.exists(LEVEL_CONFIG_PATH):
            with open(LEVEL_CONFIG_PATH, 'r') as f:
                level_config = json.load(f)
                exam_module = level_config.get("module", "")
                exam_challenge = level_config.get("challenge", "")
                logger.info(f"Loaded exam info: {exam_module}/{exam_challenge}")
    except Exception as e:
        logger.error(f"Error reading exam info from {LEVEL_CONFIG_PATH}: {e}")
    
    # Get exam administration type from API
    if pwn_college_id and exam_module and exam_challenge:
        exam_admin_type = get_exam_admin_type(pwn_college_id, exam_module, exam_challenge)
        logger.info(f"Exam administration type set to: {exam_admin_type}")
    else:
        logger.warning("Could not determine exam admin type - using default")
        
    app.run(debug=True, host='0.0.0.0', port=5000)
