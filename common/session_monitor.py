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
from datetime import datetime, timezone, timedelta
import logging

SESSION_FILE = "/challenge/.config/session.dat"

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
CHECK_INTERVAL = 60  # Check every 60 seconds
MAX_RETRIES = 3
RETRY_DELAY = 5  # Seconds between retries

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
        extract_process.communicate()
        
        if extract_process.returncode == 0:
            logger.info(f"Successfully extracted backup to {clevel_work_dir}")
        else:
            logger.error(f"Failed to extract backup, return code: {extract_process.returncode}")
            
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
    required_extensions = ['.md', '.json', '.c', '.cpp', '.rkt', '.pl']
    
    # Search for any of these file types in clevel_work_dir and subdirectories
    for root, dirs, files in os.walk(clevel_work_dir):
        for file in files:
            if any(file.endswith(ext) for ext in required_extensions):
                logger.info(f"Found required file: {os.path.join(root, file)}")
                return True
    
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
        
        # Make API request to check exam attendance
        api_url = "https://api.cse545.com/session_attendance"
        payload = {"pwn_college_id": pwn_college_id}
        
        try:
            response = requests.post(api_url, json=payload, timeout=30)
            if response.status_code == 404:
                logger.warning("Exam attendance API returned 404 - not attending")
                return {'attending': False}
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Exam attendance API response: {json.dumps(data, indent=2)}")
            
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
                    if new_end_time and new_end_time != end_time:
                        logger.info(f"Updated session end time: {new_end_time.isoformat()}")
                        new_start_time = new_start_time + timedelta(minutes=10)  # 15-minute buffer
                        end_time = new_end_time
            
            # Now check if current time is within the (possibly updated) session window
            current_time = get_current_utc_time()  # Refresh current time
            
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
