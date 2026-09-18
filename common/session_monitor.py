#!/usr/bin/env python3
"""
Session Monitor Script

This script monitors session times from api.cse545.com/session_times and ensures
the script only runs during valid session times. If the current time is outside
the session window, it will terminate process ID 1 (which kills the script).

The script is designed for systems running in UTC timezone.
"""

import os
import sys
import glob
import time
import signal
import requests
import json
import re
import subprocess
import pwd
import threading
from datetime import datetime, timezone, timedelta
import logging

SESSION_FILE = "/challenge/.config/session.dat"
EXAM_ATTEMPT_STARTUP_ID_FILE = "/opt/exam_attempt_startup_id"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/session_monitor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("session_monitor")

# Configuration
CHECK_INTERVAL = 30  # Check every 30 seconds
MAX_RETRIES = 3
RETRY_DELAY = 5  # Seconds between retries
ACTIVE_EXAM_SESSION_STATUS_API_URL = os.environ.get(
    "ACTIVE_EXAM_SESSION_STATUS_API_URL",
    "https://api.cse545.com/api/exam_container_status_v2",
)
EXAM_ADMIN_TYPE_API_URL = os.environ.get(
    "EXAM_ADMIN_TYPE_API_URL",
    "https://api.cse545.com/exam_admin_type",
)
ACTIVE_EXAM_SESSION_UNREACHABLE_LIMIT = int(os.environ.get(
    "ACTIVE_EXAM_SESSION_UNREACHABLE_LIMIT",
    "10",
))
ACTIVE_EXAM_SESSION_DEFAULT_CONTAINER_GRACE_SECONDS = int(os.environ.get(
    "ACTIVE_EXAM_SESSION_CONTAINER_GRACE_SECONDS",
    "180",
))
REPORTED_DUPLICATE_VSCODE_GROUPS = set()

def get_current_utc_time():
    """Get current time in UTC"""
    return datetime.now(timezone.utc)

def parse_iso_datetime(iso_string):
    """
    Parse ISO datetime string to datetime object
    
    Args:
        iso_string (str): ISO format datetime string
        
    Returns:
        datetime: Parsed datetime object or None if failed
    """
    try:
        # Handle different ISO formats
        if iso_string.endswith('Z'):
            iso_string = iso_string.replace('Z', '+00:00')
        
        return datetime.fromisoformat(iso_string)
    except (ValueError, TypeError) as e:
        logger.error(f"Failed to parse datetime '{iso_string}': {e}")
        return None

def check_student_exemption():
    """
    Check if student is exempted from the current problem
    
    Returns:
        dict: Dictionary with exemption status and pwn_college_id, or None if error
    """
    try:
        # Read the user_info file to get pwn_college_id
        with open('/.user_info', 'r') as f:
            user_info_content = f.read()
        
        # Extract pwn_college_id using regex
        match = re.search(r"pwn_college_id=['\"]?(\d+)['\"]?", user_info_content)
        
        if not match:
            logger.error("Could not find pwn_college_id in /.user_info")
            return None
        
        pwn_college_id = match.group(1)
        logger.info(f"Extracted pwn_college_id for exemption check: {pwn_college_id}")
        
        # Read level.json to get module and challenge information
        try:
            with open('/challenge/.config/level.json', 'r') as f:
                level_data = json.load(f)
                module = level_data.get('module')
                challenge = level_data.get('challenge') or level_data.get('level')
                
                if not module or not challenge:
                    logger.error("Could not find module or challenge in level.json")
                    return None
                    
            logger.info(f"Found module: {module}, challenge: {challenge}")
            
        except FileNotFoundError:
            logger.error("/challenge/.config/level.json not found")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse level.json: {e}")
            return None
        
        # API token from the system
        api_token = "08b26e01b8d9cb4f262da37836912504104296c33ab658dca836d032bc47b2ff"
        
        # Make API request to check exemption
        api_url = "https://api.cse545.com/is_exempt"
        payload = {
            "pwn_college_id": pwn_college_id,
            "module": module,
            "challenge": challenge,
            "api_token": api_token
        }
        
        try:
            logger.info(f"Checking exemption at {api_url}")
            response = requests.post(api_url, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Exemption API response: {json.dumps(data, indent=2)}")
            
            return {
                'pwn_college_id': data.get('pwn_college_id'),
                'is_exempt': data.get('is_exempt', False)
            }
            
        except requests.exceptions.RequestException as e:            
            logger.error(f"Failed to check exemption: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse exemption response: {e}")
            return None
            
    except FileNotFoundError:
        logger.error("/.user_info file not found")
        return None
    except Exception as e:
        logger.error(f"Unexpected error checking exemption: {e}")
        return None

def get_exam_admin_type():
    """
    Get exam administration type from API endpoint
    
    Returns:
        str: Exam administration type, defaults to "Proctoring plus Lockdown Browser" on error
    """
    try:
        # Read the user_info file to get pwn_college_id
        with open('/.user_info', 'r') as f:
            user_info_content = f.read()
        
        # Extract pwn_college_id using regex
        match = re.search(r"pwn_college_id=['\"]?(\d+)['\"]?", user_info_content)
        
        if not match:
            logger.error("Could not find pwn_college_id in /.user_info")
            return "Proctoring plus Lockdown Browser"
        
        pwn_college_id = match.group(1)
        
        # Read level.json to get module and challenge information
        try:
            with open('/challenge/.config/level.json', 'r') as f:
                level_data = json.load(f)
                module = level_data.get('module')
                challenge = level_data.get('challenge') or level_data.get('level')
                
                if not module or not challenge:
                    logger.error("Could not find module or challenge in level.json")
                    return "Proctoring plus Lockdown Browser"
                    
            logger.info(f"Checking exam admin type for module: {module}, challenge: {challenge}")
            
        except FileNotFoundError:
            logger.error("/challenge/.config/level.json not found")
            return "Proctoring plus Lockdown Browser"
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse level.json: {e}")
            return "Proctoring plus Lockdown Browser"
        
        # API token and URL
        api_token = "08b26e01b8d9cb4f262da37836912504104296c33ab658dca836d032bc47b2ff"
        api_url = EXAM_ADMIN_TYPE_API_URL
        
        payload = {
            "api_token": api_token,
            "pwn_college_id": int(pwn_college_id),
            "module": module,
            "challenge": challenge
        }
        
        try:
            logger.info(f"Requesting exam admin type from {api_url}")
            response = requests.post(api_url, json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                admin_type = data.get('exam_administration_type', 'Proctoring plus Lockdown Browser')
                logger.info(f"Exam administration type: {admin_type}")
                return admin_type
            else:
                logger.error(f"Exam admin type API returned status {response.status_code}")
                return "Proctoring plus Lockdown Browser"
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get exam admin type: {e}")
            return "Proctoring plus Lockdown Browser"
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse exam admin type response: {e}")
            return "Proctoring plus Lockdown Browser"
            
    except FileNotFoundError:
        logger.error("/.user_info file not found")
        return "Proctoring plus Lockdown Browser"
    except Exception as e:
        logger.error(f"Unexpected error getting exam admin type: {e}")
        return "Proctoring plus Lockdown Browser"

def normalized_exam_admin_type(value):
    return (value or "").strip().lower().replace("_", " ").replace("-", " ")

def is_honorlock_exam_type(value):
    return normalized_exam_admin_type(value).replace(" ", "") == "honorlock"

def requires_attendance_monitoring_for_exam_type(value):
    return normalized_exam_admin_type(value) in {
        "proctoring",
        "proctoring plus lockdown browser",
    }

def active_exam_session_monitor_enabled():
    env_value = os.environ.get("ACTIVE_EXAM_SESSION_MONITOR_ENABLED", "")
    if env_value.lower() in {"1", "true", "yes", "on"}:
        return True

    try:
        with open('/challenge/.config/level.json', 'r') as f:
            level_data = json.load(f)
        return bool(level_data.get("active_exam_session_monitor"))
    except Exception as e:
        logger.info(f"Active exam session monitor not enabled by level config: {e}")
        return False

def get_container_exam_context():
    try:
        with open('/.user_info', 'r') as f:
            user_info_content = f.read()

        match = re.search(r"pwn_college_id=['\"]?(\d+)['\"]?", user_info_content)
        if not match:
            logger.error("Could not find pwn_college_id in /.user_info")
            return None

        with open('/challenge/.config/level.json', 'r') as f:
            level_data = json.load(f)

        module = level_data.get('module')
        challenge = level_data.get('challenge') or level_data.get('examLevel') or level_data.get('level')
        if not module or not challenge:
            logger.error("Could not find module or challenge in level.json")
            return None

        startup_id = None
        try:
            with open(EXAM_ATTEMPT_STARTUP_ID_FILE) as f:
                startup_id = f.read().strip() or None
        except Exception as e:
            logger.info(f"Could not read startup id from {EXAM_ATTEMPT_STARTUP_ID_FILE}: {e}")

        return {
            "pwn_college_id": match.group(1),
            "module": module,
            "challenge": challenge,
            "startup_id": startup_id,
        }
    except FileNotFoundError as e:
        logger.error(f"Missing required context file: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse level.json: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error loading container exam context: {e}")
        return None

def check_active_exam_session_status(context):
    payload = {
        "pwn_college_id": context["pwn_college_id"],
        "module": context["module"],
        "challenge": context["challenge"],
    }
    if context.get("startup_id"):
        payload["startup_id"] = context["startup_id"]

    try:
        logger.info(
            "Checking active exam session status for "
            f"{context['pwn_college_id']} {context['module']}/{context['challenge']}"
        )
        response = requests.post(ACTIVE_EXAM_SESSION_STATUS_API_URL, json=payload, timeout=10)
        try:
            result = response.json()
        except json.JSONDecodeError:
            logger.error(f"Active exam session API returned invalid JSON with status {response.status_code}")
            return None

        result["http_status"] = response.status_code
        logger.info(f"Active exam session API response: {json.dumps(result, indent=2)}")
        return result
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to check active exam session status: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected active exam session status error: {e}")
        return None

def extract_encrypted_files():
    """Extract encrypted backup files to the challenge level directory"""
    try:
        # Read level.json to get the target directory
        with open('/challenge/.config/level.json', 'r') as f:
            level_data = json.load(f)
            clevel_work_dir = f"{level_data['hwdir']}/{level_data['level']}"
        
        logger.info(f"Extracting backup to: {clevel_work_dir}")
        
        # Check for the encrypted backup file
        encrypted_filepath = '/tmp/encrypted_clevel_work.tar.gz.enc'
        if not os.path.exists(encrypted_filepath):
            logger.warning(f"Encrypted backup file not found: {encrypted_filepath}")
            return
        
        logger.info(f"Found backup file: {encrypted_filepath}")
        
        # Decrypt and extract in one command
        # Check if helper file exists
        helper_file = '/.helper'
        if not os.path.exists(helper_file):
            logger.warning(f"Helper file not found: {helper_file}")
            return
        
        if not os.path.exists(encrypted_filepath):
            logger.warning(f"Encrypted backup file not found: {encrypted_filepath}")
            return
        
        # Read password from helper file
        try:
            with open(helper_file, 'r') as f:
                password = f.read().strip()
        except Exception as e:
            logger.error(f"Error reading password from {helper_file}: {e}")
            return
        
        decrypt_cmd = ['openssl', 'enc', '-aes-256-cbc', '-d', '-pbkdf2', '-pass', f'pass:{password}', '-in', encrypted_filepath]
        extract_cmd = ['tar', '-xzf', '-', '-C', clevel_work_dir, '--strip-components=1']
        
        # Create the target directory if it doesn't exist
        os.makedirs(clevel_work_dir, exist_ok=True)
        
        # Run decrypt | extract pipeline
        decrypt_process = subprocess.Popen(decrypt_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        extract_process = subprocess.Popen(extract_cmd, stdin=decrypt_process.stdout, stderr=subprocess.PIPE)
        decrypt_process.stdout.close()
        
        # Wait for completion
        extract_stdout, extract_stderr = extract_process.communicate()
        
        if extract_process.returncode == 0:
            logger.info(f"Successfully extracted backup to {clevel_work_dir}")
            # Log what was extracted
            try:
                for root, dirs, files in os.walk(clevel_work_dir):
                    logger.info(f"Extracted directory: {root}")
                    for file in files:
                        logger.info(f"  Extracted file: {file}")
            except Exception as e:
                logger.error(f"Error listing extracted files: {e}")
        else:
            logger.error(f"Failed to extract backup, return code: {extract_process.returncode}")
            if extract_stderr:
                logger.error(f"Extract stderr: {extract_stderr.decode('utf-8', errors='ignore')}")
            
    except Exception as e:
        logger.error(f"Error extracting backup files: {e}")

def check_for_required_files(clevel_work_dir):
    """
    Check if required files exist in clevel_work_dir.
    
    Args:
        clevel_work_dir (str): Path to the directory to check
        
    Returns:
        bool: True if required files are found, False otherwise
    """
    # Define file extensions to search for
    required_extensions = ['.c', '.cpp', '.rkt', '.pl']
    
    # First check if the directory exists
    if not os.path.exists(clevel_work_dir):
        logger.warning(f"Directory does not exist: {clevel_work_dir}")
        return False
    
    # Check if we can access the directory
    if not os.access(clevel_work_dir, os.R_OK):
        logger.warning(f"Directory exists but not readable: {clevel_work_dir}")
        return False
    
    # Log directory permissions and ownership
    try:
        stat_info = os.stat(clevel_work_dir)
        logger.info(f"Directory stats: mode={oct(stat_info.st_mode)}, uid={stat_info.st_uid}, gid={stat_info.st_gid}")
    except Exception as e:
        logger.error(f"Failed to stat directory: {e}")
    
    # Search for any of these file types in clevel_work_dir and subdirectories
    files_found_list = []
    for root, dirs, files in os.walk(clevel_work_dir):
        for file in files:
            # Check if file matches required extensions (case-insensitive) or is README.md
            if any(file.lower().endswith(ext) for ext in required_extensions) or file.lower() == 'readme.md':
                full_path = os.path.join(root, file)
                files_found_list.append(full_path)
                logger.info(f"Found required file: {full_path}")
                # Check file permissions
                try:
                    stat_info = os.stat(full_path)
                    logger.info(f"  File stats: mode={oct(stat_info.st_mode)}, uid={stat_info.st_uid}, gid={stat_info.st_gid}, size={stat_info.st_size}")
                except Exception as e:
                    logger.error(f"  Failed to stat file: {e}")
    
    if files_found_list:
        logger.info(f"Total required files found: {len(files_found_list)}")
        return True
    
    logger.warning(f"No required files found in {clevel_work_dir}")
    return False

def check_and_restore_clevel_work_dir():
    """
    Check if clevel_work_dir has required files and restore from backup if missing.
    
    Returns:
        bool: True if files exist or were successfully restored, False otherwise
    """
    try:
        # Build clevel_work_dir path
        with open('/challenge/.config/level.json', 'r') as f:
            level_data = json.load(f)
            clevel_work_dir = f"{level_data['hwdir']}/{level_data['level']}"
        
        logger.info(f"Checking files in clevel_work_dir: {clevel_work_dir}")
        
        # Check if directory exists
        if not os.path.exists(clevel_work_dir):
            logger.warning(f"clevel_work_dir does not exist: {clevel_work_dir}")
            logger.info("Attempting to extract from backup...")
            extract_encrypted_files()
            
            # Verify extraction worked by checking again
            if not os.path.exists(clevel_work_dir):
                logger.error(f"Extraction failed - directory still does not exist: {clevel_work_dir}")
                return False
        
        # Check for required files
        if check_for_required_files(clevel_work_dir):
            logger.info(f"Required files found in {clevel_work_dir}, no restoration needed")
            return True
        
        # No files found, attempt extraction
        logger.warning(f"No required files (.md, .json, .c, .cpp, .rkt, .pl) found in {clevel_work_dir}")
        logger.info("Attempting to extract from backup...")
        extract_encrypted_files()
        
        # Verify extraction worked by checking for files again
        if check_for_required_files(clevel_work_dir):
            logger.info("Successfully extracted and verified backup files")
            return True
        else:
            logger.error("Extraction completed but no required files found")
            return False
            
    except FileNotFoundError:
        logger.error("/challenge/.config/level.json not found")
        return False
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse level.json: {e}")
        return False
    except Exception as e:
        logger.error(f"Error checking clevel_work_dir: {e}")
        return False


def handle_exempted_student():
    """
    Handle the case where a student is exempted from the problem.
    Broadcasts the flag, writes to /flag_exempted, and adds to bash.bashrc
    """
    try:
        # Read the flag
        with open('/flag', 'r') as f:
            flag_content = f.read().strip()
        
        logger.info("Student is exempted - providing flag")
        
        # Broadcast the flag to all terminals
        flag_message = f"\n*** EXEMPTED STUDENT FLAG ***\n{flag_content}\n*** You are exempted from this problem ***\n"
        broadcast_message(flag_message)
        
        # Write flag to /flag_exempted
        with open('/flag_exempted', 'w') as f:
            f.write(flag_content + '\n')
        os.chmod('/flag_exempted', 0o644)
        logger.info("Flag written to /flag_exempted")
        
        # Add statement to /etc/bash.bashrc to print the flag with color coding
        bashrc_statement = f'\n# Exempted student flag display\necho -e "\\033[1;32m\\n{flag_content}\\n\\033[0m"\n'
        
        try:
            with open('/etc/bash.bashrc', 'a') as f:
                f.write(bashrc_statement)
            logger.info("Flag display statement added to /etc/bash.bashrc")
        except Exception as e:
            logger.error(f"Failed to write to /etc/bash.bashrc: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error handling exempted student: {e}")
        return False

def check_exam_attendance():
    """
    Extract pwn_college_id from /.user_info and check exam attendance status
    
    Returns:
        dict: Dictionary with 'attending' status, optional 'container_action', and 'session_info', or None if error
    """
    try:
        # Read the user_info file
        with open('/.user_info', 'r') as f:
            user_info_content = f.read()
        
        # Extract pwn_college_id using regex
        # Looking for pattern like pwn_college_id='130143'
        match = re.search(r"pwn_college_id=['\"]?(\d+)['\"]?", user_info_content)
        
        if not match:
            logger.error("Could not find pwn_college_id in /.user_info")
            return None
        
        pwn_college_id = match.group(1)
        logger.info(f"Extracted pwn_college_id: {pwn_college_id}")
        
        # Check for admin override first
        if check_admin_override():
            logger.info(f"Admin override active for pwn_college_id: {pwn_college_id}")
            # Create a fake attendance result with extended session times
            current_time = get_current_utc_time()
            return {
                'attending': True,
                'container_action': None,
                'session_info': {
                    'start_time_utc': (current_time - timedelta(days=1)).isoformat(),
                    'end_time_utc': (current_time + timedelta(days=365)).isoformat(),
                    'type': 'admin_override'
                }
            }
        
        module = None
        challenge = None
        try:
            with open('/challenge/.config/level.json', 'r') as f:
                level_data = json.load(f)
                module = level_data.get('module')
                challenge = level_data.get('challenge') or level_data.get('examLevel') or level_data.get('level')
        except Exception as e:
            logger.warning(f"Could not load exam context for attendance check: {e}")

        # Make API request to check exam attendance
        api_url = "https://api.cse545.com/session_attendance"
        payload = {
            "pwn_college_id": pwn_college_id,
            "module": module,
            "challenge": challenge,
        }
        
        try:
            response = requests.post(api_url, json=payload, timeout=30)
            if response.status_code == 404:
                logger.warning("Exam attendance API returned 404 - not attending")
                return {'attending': False}
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Exam attendance API response: {json.dumps(data, indent=2)}")
            
            # Check valid_session field to determine if a proctor session exists
            valid_session = data.get('valid_session', False)
            if not valid_session:
                logger.warning(f"No valid proctor session found: {data.get('message', 'Unknown reason')}")
                return {'attending': False}
            
            # Return the attending status, container action, and session info
            result = {
                'attending': data.get('attending', False),
                'container_action': data.get('container_action'),
                'session_info': data.get('session_info')
            }
            logger.info(f"Exam attendance status: {result['attending']}")
            if result['container_action']:
                logger.info(f"Container action: {result['container_action']}")
            if result['session_info']:
                logger.info(f"Session info received: {result['session_info']}")
            return result
            
        except requests.exceptions.RequestException as e:            
            logger.exception("request failed")
            logger.error(f"Failed to check exam attendance: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.exception("request failed")
            logger.error(f"Failed to parse exam attendance response: {e}")
            return None
            
    except FileNotFoundError:
        logger.error("/.user_info file not found")
        return None
    except Exception as e:
        logger.error(f"Unexpected error checking exam attendance: {e}")
        return None

def check_admin_override():
    """
    Check if current user is in /.helperids for admin override
    
    Returns:
        bool: True if user is an admin, False otherwise
    """
    try:
        # Extract pwn_college_id from .user_info
        with open('/.user_info', 'r') as f:
            user_info_content = f.read()
        match = re.search(r"pwn_college_id=['\"]?(\d+)['\"]?", user_info_content)
        
        if not match:
            return False
        
        current_pwn_id = match.group(1)
        
        # Check if this pwn_college_id is in /.helperids
        if os.path.exists('/.helperids'):
            with open('/.helperids', 'r') as f:
                helper_ids = [line.strip() for line in f if line.strip()]
            
            if current_pwn_id in helper_ids:
                logger.info(f"Admin override: pwn_college_id {current_pwn_id} found in /.helperids")
                return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking admin override: {e}")
        return False

def check_and_report_duplicate_vscode():
    """
    Check for duplicate VSCode extension host processes and report them.
    Looks for processes containing both '/code-server/' and '--type=extensionHost' in their command line.
    """
    try:
        global REPORTED_DUPLICATE_VSCODE_GROUPS
        import psutil
        
        # Find all extension host processes
        extension_hosts = []
        
        for proc in psutil.process_iter(['pid', 'cmdline', 'ppid']):
            try:
                cmdline = proc.info['cmdline']
                if cmdline:
                    cmdline_str = ' '.join(cmdline)
                    # Check if this is a code-server extension host
                    if '/code-server/' in cmdline_str and '--type=extensionHost' in cmdline_str:
                        extension_hosts.append({
                            'pid': proc.info['pid'],
                            'ppid': proc.info['ppid'],
                            'cmdline': cmdline_str
                        })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        if len(extension_hosts) < 2:
            logger.info(f"Found {len(extension_hosts)} VSCode extension host process(es), no duplicates to report")
            return
        
        # Group by parent PID to find duplicates with same parent
        from collections import defaultdict
        by_parent = defaultdict(list)
        for host in extension_hosts:
            by_parent[host['ppid']].append(host)
        
        # Find parents with multiple extension hosts
        reported_any = False
        for ppid, hosts in by_parent.items():
            if len(hosts) >= 2:
                # Sort by PID and report the highest PID as the extra extension host.
                hosts_sorted = sorted(hosts, key=lambda x: x['pid'], reverse=True)
                to_report = hosts_sorted[0]
                report_key = (ppid, tuple(sorted(host['pid'] for host in hosts)))
                
                logger.warning(f"Found {len(hosts)} extension hosts with same parent (ppid={ppid})")
                logger.warning(f"Reporting duplicate VSCode extension host with highest PID: {to_report['pid']}")

                if report_key in REPORTED_DUPLICATE_VSCODE_GROUPS:
                    logger.info(f"Duplicate VSCode group already reported for parent {ppid}")
                    reported_any = True
                    continue
                
                try:
                    reported_any = True
                    
                    # Broadcast message to student
                    # broadcast_message("\n⚠️  Duplicate VSCode instance detected and reported, this will be investigated and you will receive an AIV if multiple instances have been used on the exam.\n")
                    
                    # Report to API
                    try:
                        # Get student and challenge info
                        with open('/.user_info', 'r') as f:
                            user_info_content = f.read()
                        match = re.search(r"pwn_college_id=['\"]?(\d+)['\"]?", user_info_content)
                        pwn_college_id = match.group(1) if match else "unknown"
                        
                        # Get module and challenge from level.json
                        try:
                            with open('/challenge/.config/level.json', 'r') as f:
                                level_data = json.load(f)
                                module = level_data.get('module', 'unknown')
                                challenge = level_data.get('challenge') or level_data.get('level', 'unknown')
                        except:
                            module = "unknown"
                            challenge = "unknown"
                        
                        # API token
                        api_token = "08b26e01b8d9cb4f262da37836912504104296c33ab658dca836d032bc47b2ff"
                        
                        # Report to API
                        api_url = "https://api.cse545.com/duplicate_vscode_detected"
                        payload = {
                            "pwn_college_id": pwn_college_id,
                            "module": module,
                            "challenge": challenge,
                            "num_duplicates": len(hosts),
                            "flagged_pid": to_report['pid'],
                            "killed_pid": to_report['pid'],
                            "parent_pid": ppid,
                            "action": "reported_only",
                            "killed": False,
                            "api_token": api_token
                        }
                        
                        response = requests.post(api_url, json=payload, timeout=10)
                        if response.status_code == 200:
                            logger.info(f"Successfully reported duplicate VSCode to API")
                            REPORTED_DUPLICATE_VSCODE_GROUPS.add(report_key)
                        else:
                            logger.warning(f"API reported duplicate with status {response.status_code}")
                    except Exception as e:
                        logger.error(f"Failed to report duplicate VSCode to API: {e}")
                    
                except ProcessLookupError:
                    logger.warning(f"Process {to_report['pid']} no longer exists")
                except PermissionError:
                    logger.error(f"Permission denied to inspect process {to_report['pid']}")
                except Exception as e:
                    logger.error(f"Failed to report process {to_report['pid']}: {e}")
        
        if not reported_any:
            logger.info(f"Found {len(extension_hosts)} extension hosts but none share the same parent")
            
    except ImportError:
        logger.error("psutil module not available, cannot check for duplicate VSCode processes")
    except Exception as e:
        logger.error(f"Error checking for duplicate VSCode processes: {e}")

def check_and_kill_duplicate_vscode():
    """Backward-compatible wrapper; duplicate VSCode detection is report-only."""
    check_and_report_duplicate_vscode()

def broadcast_message(message):
    for tty in glob.glob("/dev/pts/[0-9]*"):
        try:
            with open(tty, "w") as f:
                f.write(message)
            logging.info(f"Broadcasted to {tty}: {message.strip()}")
        except Exception as e:
            logging.info(f"Failed to write to {tty}: {e}")

def kill_process_1():
    """Kill process 1 to shutdown the container"""
    logger.critical("Killing process 1 to shutdown container")
    try:
        os.kill(1, signal.SIGTERM)
    except Exception as e:
        logger.error(f"Failed to kill process 1: {e}")
        try:
            os.kill(1, signal.SIGKILL)
        except Exception as e2:
            logger.error(f"Failed to force kill process 1: {e2}")

def watch_for_killme():
    """Background thread that watches for /tmp/.killme file and kills container immediately"""
    logger.info("Started killme watcher thread")
    while True:
        try:
            if os.path.exists('/tmp/.killme'):
                logger.critical("Found /tmp/.killme file - immediate shutdown requested")
                kill_process_1()
                break
        except Exception as e:
            logger.error(f"Error checking for /tmp/.killme: {e}")
        time.sleep(1)  # Check every second

def mark_session_paused(message=None):
    """
    Pause the session by marking it as terminated
    """
    # Check for user id 132329 in /.user_info
    try:
        with open('/.user_info', 'r') as f:
            user_info = f.read()        
    except Exception as e:
        logger.error(f"Error reading /.user_info: {e}")
    
    try:
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, 'r') as f:
                    content = f.read().strip()
                if content == "terminated":
                    logger.info("Session already marked as terminated, skipping termination.")
                    return
            except Exception as e:
                logger.error(f"Error reading {SESSION_FILE}: {e}")
        
        with open(SESSION_FILE, 'w') as f:
            f.write("terminated\n")
        os.chown(SESSION_FILE, 0, 0)
        os.chmod(SESSION_FILE, 0o644)
        if message:
            broadcast_message(message)
        else:
            broadcast_message("Session marked inactive, tester will no longer return the flag once all tests are passed. If currently in a testing session, check with staff person to restart the session.")
    
    except Exception as e:
        logger.error(f"Error reading {SESSION_FILE}: {e}")

def mark_session_active():
    """
    Mark the session as active
    """
    try:
        with open(SESSION_FILE, 'w') as f:
            f.write("active\n")
        os.chown(SESSION_FILE, 0, 0)
        os.chmod(SESSION_FILE, 0o644)
    except Exception as e:
        logger.error(f"Error reading {SESSION_FILE}: {e}")
    except Exception as e:
        logger.error(f"Error reading {SESSION_FILE}: {e}")
        return False

def write_container_dead_marker(reason):
    try:
        with open('/challenge/.dead', 'w') as f:
            f.write(f"{get_current_utc_time().isoformat()} {reason}\n")
        logger.info("Created /challenge/.dead for active exam session shutdown")
    except Exception as e:
        logger.error(f"Failed to create /challenge/.dead: {e}")

def monitor_active_exam_session():
    """Monitor the browser launcher heartbeat for Honorlock-style active sessions."""
    logger.info("Starting active exam session monitor")

    context = get_container_exam_context()
    if not context:
        logger.error("Could not load active exam session context; failing open to avoid accidental lockout")
        mark_session_active()
        check_and_restore_clevel_work_dir()
        return

    if not os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'w') as f:
            f.write("inactive\n")
        os.chown(SESSION_FILE, 0, 0)
        os.chmod(SESSION_FILE, 0o644)

    first_time = True
    was_active = False
    files_restored = False
    unreachable_checks = 0
    stale_since = None
    stale_reason = None

    while True:
        try:
            if first_time:
                first_time = False
            else:
                time.sleep(CHECK_INTERVAL)

            result = check_active_exam_session_status(context)
            current_time = get_current_utc_time()

            if result is None:
                unreachable_checks += 1
                logger.warning(
                    "Active exam session status unavailable "
                    f"({unreachable_checks}/{ACTIVE_EXAM_SESSION_UNREACHABLE_LIMIT})"
                )
                if unreachable_checks >= ACTIVE_EXAM_SESSION_UNREACHABLE_LIMIT:
                    mark_session_paused(
                        "The exam monitoring service could not be reached for several minutes. "
                        "Your container is still running, but the tester will not return the flag. "
                        "Please contact course staff.\n"
                    )
                    was_active = False
                continue

            unreachable_checks = 0
            allowed = bool(result.get("allowed"))
            reason = result.get("reason", "unknown")

            if allowed:
                if not was_active:
                    logger.info("Active exam session recovered or became active")
                    broadcast_message("Exam monitoring connection is active. You can continue working.\n")
                mark_session_active()
                check_and_report_duplicate_vscode()
                was_active = True
                stale_since = None
                stale_reason = None
                if not files_restored:
                    logger.info("Active exam session is active - checking/restoring clevel_work_dir files")
                    if check_and_restore_clevel_work_dir():
                        files_restored = True
                        logger.info("Files check/restore completed successfully")
                    else:
                        logger.warning("Files check/restore failed, will retry next loop")
                continue

            if stale_since is None:
                stale_since = current_time
                stale_reason = reason
                logger.critical(f"Active exam session is not allowed: {reason}")
                mark_session_paused(
                    "Your exam monitoring page is no longer active. "
                    "Your container is still running for now, but the tester will not return the flag. "
                    "Please return to the exam launcher page or contact course staff.\n"
                )
                was_active = False
                continue

            stale_elapsed = (current_time - stale_since).total_seconds()
            container_grace_seconds = int(
                result.get("container_grace_seconds")
                or ACTIVE_EXAM_SESSION_DEFAULT_CONTAINER_GRACE_SECONDS
            )
            logger.warning(
                "Active exam session still blocked: "
                f"reason={reason}, first_reason={stale_reason}, stale_elapsed={stale_elapsed:.0f}s"
            )

            if stale_elapsed >= container_grace_seconds:
                logger.critical("Active exam session stale grace exceeded; shutting down container")
                broadcast_message(
                    "The exam monitoring page has been inactive for too long. "
                    "This container is shutting down. Please contact course staff.\n"
                )
                write_container_dead_marker(reason)
                time.sleep(15)
                kill_process_1()

        except KeyboardInterrupt:
            logger.info("Received interrupt signal - exiting active exam session monitor")
            return
        except Exception as e:
            logger.error(f"Unexpected error in active exam session monitor: {e}")

def is_time_in_session(current_time, start_time, end_time):
    """
    Check if current time is within session window
    
    Args:
        current_time (datetime): Current UTC time
        start_time (datetime): Session start time
        end_time (datetime): Session end time
        
    Returns:
        bool: True if within session, False otherwise
    """
    # Ensure all times are timezone-aware UTC
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    
    # Convert all to UTC for comparison
    current_utc = current_time.astimezone(timezone.utc)
    start_utc = start_time.astimezone(timezone.utc)
    end_utc = end_time.astimezone(timezone.utc)
    
    logger.info(f"Time comparison (UTC):")
    logger.info(f"  Current: {current_utc.isoformat()}")
    logger.info(f"  Start:   {start_utc.isoformat()}")
    logger.info(f"  End:     {end_utc.isoformat()}")
    
    is_within = start_utc <= current_utc <= end_utc
    logger.info(f"  Within session: {is_within}")
    
    return is_within

def is_attendance_only_session(session_info):
    """Return True when attendance, not session_times, is the live authority."""
    return (session_info or {}).get('type') == 'honorlock_attendance'

def get_session_times():
    """
    Get session start and end times from attendance check, or use defaults
    
    Returns:
        tuple: (start_time, end_time) as datetime objects
    """
    # Get session times from attendance check
    attendance_result = check_exam_attendance()
    start_time = None
    end_time = None 
    
    if attendance_result and attendance_result.get('session_info'):
        session_info = attendance_result['session_info']
        if is_attendance_only_session(session_info):
            logger.info("Honorlock attendance session found; session stays active while attendance remains open")
            start_time = get_current_utc_time() - timedelta(minutes=5)
            end_time = get_current_utc_time() + timedelta(seconds=CHECK_INTERVAL * 2)
            return start_time, end_time

        logger.info("Valid session found from attendance check, using provided session times")
        start_time_str = session_info.get('start_time_utc')
        end_time_str = session_info.get('end_time_utc')
        
        # Parse the datetime strings (they may already be ISO format)
        if isinstance(start_time_str, str):
            start_time = parse_iso_datetime(start_time_str)
        if isinstance(end_time_str, str):
            end_time = parse_iso_datetime(end_time_str)
        
        if start_time and end_time:
            start_time = start_time - timedelta(minutes=5)  # 5-minute buffer
            logger.info(f"Session found: {session_info.get('type', 'unknown')}")

    if start_time is None or end_time is None:
        logger.info("No valid session times found from attendance check, using defaults")
        default_minutes = 60
        logger.info(f"Using default_session_time: {default_minutes} minutes")
        # to make sure current_time is inside session
        start_time = get_current_utc_time() - timedelta(seconds=5)
        end_time = start_time + timedelta(minutes=default_minutes)            
            
    logger.info(f"Session start (UTC): {start_time.isoformat()}")
    logger.info(f"Session end (UTC): {end_time.isoformat()}")
    
    return start_time, end_time

def main():
    """Main monitoring loop"""
    logger.info("Session Monitor starting...")
    logger.info(f"Process ID: {os.getpid()}")
    logger.info(f"Parent Process ID: {os.getppid()}")
    current_time = get_current_utc_time()
    logger.info(f"Current UTC time: {current_time.isoformat()}")

    logger.info("Checking exam administration type...")
    exam_admin_type = get_exam_admin_type()
    logger.info(f"Exam administration type: {exam_admin_type}")

    if active_exam_session_monitor_enabled() and is_honorlock_exam_type(exam_admin_type):
        logger.info("Active exam session monitor is enabled for Honorlock by level config")
        monitor_active_exam_session()
        return
    if active_exam_session_monitor_enabled():
        logger.info(
            "Active exam session monitor is enabled by level config, but exam type "
            f"'{exam_admin_type}' is not Honorlock; using legacy monitoring path"
        )
    
    # Check if this exam type requires attendance monitoring
    requires_attendance_monitoring = requires_attendance_monitoring_for_exam_type(exam_admin_type)
    
    if not requires_attendance_monitoring:
        logger.info(f"Exam type '{exam_admin_type}' does not require attendance monitoring")
        logger.info("Setting session.dat to active and exiting")
        
        # Set session to active and exit
        try:
            with open(SESSION_FILE, 'w') as f:
                f.write("active\n")
            os.chown(SESSION_FILE, 0, 0)
            os.chmod(SESSION_FILE, 0o644)
            logger.info(f"Set {SESSION_FILE} to active - monitoring not needed")
            check_and_restore_clevel_work_dir()
        except Exception as e:
            logger.error(f"Error setting session.dat: {e}")
        
        return  # Exit - no monitoring needed
    
    # If we get here, this exam type requires attendance monitoring
    logger.info(f"Exam type '{exam_admin_type}' requires attendance monitoring - starting monitor loop")

    # Get session times
    start_time, end_time = get_session_times()
    
    # Check if student is exempted from this problem
    logger.info("Checking if student is exempted from this problem...")
    exemption_result = check_student_exemption()
    
    if exemption_result and exemption_result.get('is_exempt', False):
        logger.info(f"Student {exemption_result.get('pwn_college_id')} is exempted from this problem")
        
        # Handle exempted student - provide flag and exit
        if handle_exempted_student():
            logger.info("Successfully handled exempted student, exiting session monitor")
            return
        else:
            logger.error("Failed to handle exempted student properly")
    else:
        if exemption_result:
            logger.info(f"Student {exemption_result.get('pwn_college_id')} is NOT exempted, continuing normal session monitoring")
        else:
            logger.info("Could not determine exemption status, continuing normal session monitoring")
    
    ############################################

    first_time = True 
    if not os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, 'w') as f:
            f.write("inactive\n")
        os.chown(SESSION_FILE, 0, 0)
        os.chmod(SESSION_FILE, 0o644)

    missing_attendance = 0
    was_active = False  # Track if we were previously active
    files_restored = False  # Track if we've successfully checked/restored files
    time_bound_session = True
    # Main monitoring loop
    while True:
        try:
            if first_time:
                # no sleep on first entry
                first_time = False
            else:
                time.sleep(CHECK_INTERVAL)
            current_time = get_current_utc_time()
            logger.info(f"Checking session status at {current_time.isoformat()}")
            
            # Check if session has ended
            if current_time > end_time or not is_time_in_session(current_time, start_time, end_time):
                logger.info("Session time check failed, will refresh times from next attendance check")
            
            # Check attendance and get updated session info
            check_results = check_exam_attendance()
            
            # Update session times if we received session_info
            if check_results and check_results.get('session_info'):
                session_info = check_results['session_info']
                if is_attendance_only_session(session_info):
                    if time_bound_session:
                        logger.info("Switching to Honorlock attendance monitoring without fixed session times")
                    time_bound_session = False
                    start_time = current_time - timedelta(minutes=5)
                    end_time = current_time + timedelta(seconds=CHECK_INTERVAL * 2)
                else:
                    time_bound_session = True
                    start_time_str = session_info.get('start_time_utc')
                    end_time_str = session_info.get('end_time_utc')

                    # Parse and update session times
                    if isinstance(start_time_str, str):
                        new_start_time = parse_iso_datetime(start_time_str)
                        if new_start_time:
                            new_start_time = new_start_time - timedelta(minutes=15)  # 15-minute buffer
                            if new_start_time != start_time:
                                logger.info(f"Updated session start time: {new_start_time.isoformat()}")
                                start_time = new_start_time

                    if isinstance(end_time_str, str):
                        new_end_time = parse_iso_datetime(end_time_str)
                        if new_end_time:
                            new_end_time = new_end_time + timedelta(minutes=10)  # 10-minute buffer
                            if new_end_time != end_time:
                                logger.info(f"Updated session end time: {new_end_time.isoformat()}")
                                end_time = new_end_time
            
            # Now check if current time is within the (possibly updated) session window
            current_time = get_current_utc_time()  # Refresh current time
            
            if time_bound_session:
                if current_time > end_time:
                    logger.critical("Session has paused, current time is past end time")
                    mark_session_paused()
                    continue

                if not is_time_in_session(current_time, start_time, end_time):
                    logger.critical("Current time is outside session window - terminating")
                    mark_session_paused()
                    continue

                # Calculate time remaining
                time_remaining = end_time - current_time
                minutes_remaining = int(time_remaining.total_seconds() / 60)
                logger.info(f"Session is active - {minutes_remaining} minutes remaining")
            else:
                logger.info("Honorlock attendance is active; skipping fixed session time cutoff")

            # Check for duplicate VSCode extension hosts (run regardless of attendance)
            check_and_kill_duplicate_vscode()

            # Handle attendance results
            if check_results is None :
                # nothing returned, hopefully just a communication error that will resolve soon
                missing_attendance += 1
                if missing_attendance == 3:
                    logger.critical(f"Multiple attempts to detect attendance failed, terminating session after {missing_attendance} attempts")
                    mark_session_paused(message="Multiple attempts to detect attendance failed, you will no longer be able to get the flag from running")
                    was_active = False
                    continue
            elif check_results['attending'] == True:
                # Check if we're recovering from an inactive state
                if not was_active and missing_attendance > 0:
                    logger.info("Session recovered - student is back online")
                    broadcast_message("Session recovered! You are back online and can continue your work.\n")
                
                mark_session_active()
                missing_attendance = 0
                was_active = True
                
                # Check and restore clevel_work_dir if not already done
                if not files_restored:
                    logger.info("Session is active - checking/restoring clevel_work_dir files")
                    if check_and_restore_clevel_work_dir():
                        files_restored = True
                        logger.info("Files check/restore completed successfully")
                    else:
                        logger.warning("Files check/restore failed, will retry next loop")
                
            elif check_results['attending'] == False:
                # Check if container should be shutdown
                if check_results.get('container_action') == 'shutdown':
                    logger.critical("Container shutdown requested - killing process 1")
                    broadcast_message("Container is being shutdown by instructor.\n")
                    # Create /challenge/.dead file with current timestamp
                    try:
                        with open('/challenge/.dead', 'w') as f:
                            f.write(f"{current_time.isoformat()}\n")
                        logger.info("Created /challenge/.dead with current timestamp")
                    except Exception as e:
                        logger.error(f"Failed to create /challenge/.dead: {e}")
                    
                    # Start background thread to watch for /tmp/.killme
                    watcher_thread = threading.Thread(target=watch_for_killme, daemon=True)
                    watcher_thread.start()
                    logger.info("Started killme watcher thread")
                    
                    time.sleep(15)
                    kill_process_1()
                    
                if missing_attendance < 5:
                    logger.critical("Exam attendance check failed")
                    mark_session_paused(message="You are no longer shown as logged into the exam, please contact course staff.\nYou will no longer be able to get the flag from the tester.")
                    missing_attendance += 5
                    was_active = False
                    continue
                elif missing_attendance > 5 and ((missing_attendance % 5) == 0):
                    # Every 5th time after the initial marking, remind the student
                    logger.info("Student still not attending, reminding them")
                    broadcast_message("Reminder: You are still not logged into the exam. Please contact course staff if you believe this is an error.\nYou will no longer be able to get the flag from the tester.\n")
                    missing_attendance += 1
                else:
                    missing_attendance += 1
                    logger.info("Student still not attending, already marked session as terminated inactive")

        except KeyboardInterrupt:
            logger.info("Received interrupt signal - exiting gracefully")
        except Exception as e:
            logger.error(f"Unexpected error in monitoring loop: {e}")
            #kill_process_1()
    
    # end while 

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        #kill_process_1()
