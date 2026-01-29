#!/usr/bin/env python3

import json
import subprocess
import time
import re
import logging
import glob
from datetime import datetime, timezone
from pathlib import Path
import requests
import os

# Setup logging
logging.basicConfig(
    filename='/var/log/attendance_check.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

API_URL = "https://api.cse545.com/validate_attendance"
API_TOKEN = "08b26e01b8d9cb4f262da37836912504104296c33ab658dca836d032bc47b2ff"
USER_INFO_FILE = "/.user_info"
LEVEL_CONFIG = "/challenge/.config/level.json"
FLAG_FILE = "/flag"
SAVED_FLAG_FILE = "/.saved_flag"

def get_pwn_college_id():
    """Extract pwn_college_id from /.user_info"""
    try:
        with open(USER_INFO_FILE, 'r') as f:
            content = f.read()
        match = re.search(r"pwn_college_id='(\d+)'", content)
        if match:
            return match.group(1)
        logging.error("Could not find pwn_college_id in /.user_info")
        return None
    except Exception as e:
        logging.error(f"Error reading {USER_INFO_FILE}: {e}")
        return None

def get_work_dir():
    """Get the lab's working directory from level.json"""
    try:
        with open(LEVEL_CONFIG, 'r') as f:
            level_data = json.load(f)
        hwdir = level_data.get('hwdir', '')
        level = level_data.get('level', '')
        work_dir = f"{hwdir}/{level}"
        return work_dir
    except Exception as e:
        logging.error(f"Error reading {LEVEL_CONFIG}: {e}")
        return None

def validate_attendance(pwn_college_id, module=None, challenge=None):
    """Make API request to validate attendance"""
    try:
        payload = {
            "pwn_college_id": pwn_college_id,
            "api_token": API_TOKEN
        }
        if module:
            payload["module"] = module
        if challenge:
            payload["challenge"] = challenge
        response = requests.post(API_URL, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        logging.error(f"Error making API request: {e}")
        return None

def broadcast_message(message):
    """Send broadcast message to all TTYs"""
    for tty in glob.glob("/dev/pts/[0-9]*"):
        try:
            with open(tty, "w") as f:
                f.write(message)
            logging.info(f"Broadcasted to {tty}: {message.strip()}")
        except Exception as e:
            logging.info(f"Failed to write to {tty}: {e}")

def make_files_readonly(work_dir):
    """Make all .c and .cpp files in work_dir read-only"""
    try:
        if not work_dir or not os.path.exists(work_dir):
            logging.warning(f"Work directory does not exist: {work_dir}")
            return
        
        file_count = 0
        for ext in ['*.c', '*.cpp']:
            for file in Path(work_dir).rglob(ext):
                try:
                    os.chmod(file, 0o444)
                    file_count += 1
                    logging.debug(f"Set {file} to read-only")
                except Exception as e:
                    logging.error(f"Error setting {file} to read-only: {e}")
        
        if file_count > 0:
            logging.info(f"Set {file_count} files to read-only in {work_dir}")
    except Exception as e:
        logging.error(f"Error making files read-only: {e}")

def make_files_readwrite(work_dir):
    """Make all .c and .cpp files in work_dir read-write for owner"""
    try:
        if not work_dir or not os.path.exists(work_dir):
            logging.warning(f"Work directory does not exist: {work_dir}")
            return
        
        file_count = 0
        for ext in ['*.c', '*.cpp']:
            for file in Path(work_dir).rglob(ext):
                try:
                    os.chmod(file, 0o644)  # rw-r--r--
                    file_count += 1
                    logging.debug(f"Set {file} to read-write")
                except Exception as e:
                    logging.error(f"Error setting {file} to read-write: {e}")
        
        if file_count > 0:
            logging.info(f"Set {file_count} files to read-write in {work_dir}")
    except Exception as e:
        logging.error(f"Error making files read-write: {e}")

def add_notice_to_readme(reason):
    """Add attendance violation notice to readme.html if it exists"""
    readme_path = "/challenge/.config/readme.html"
    
    if not os.path.exists(readme_path):
        logging.info(f"readme.html not found at {readme_path}, skipping notice addition")
        return
    
    try:
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if notice already exists
        notice_marker = "<!-- ATTENDANCE_VIOLATION_NOTICE -->"
        if notice_marker in content:
            logging.info("Attendance notice already present in readme.html")
            return
        
        # Create the notice HTML
        notice_html = f'''<!-- ATTENDANCE_VIOLATION_NOTICE -->
<div style="background-color: #ffebee; border: 3px solid #c62828; border-radius: 8px; padding: 20px; margin: 20px 0; font-family: Arial, sans-serif;">
    <h2 style="color: #c62828; margin-top: 0;">⚠️ CLASS LAB ATTENDANCE VIOLATION</h2>
    <p style="font-size: 16px; line-height: 1.6;">
        <strong>Class labs must be completed during scheduled class time.</strong><br>
        No more work may be done on class labs outside of class.
    </p>
    <p style="font-size: 14px; color: #000; margin-bottom: 0;">
        <strong>Reason:</strong> {reason}<br>
        <strong>Status:</strong> All .c and .cpp files have been set to read-only.
    </p>
</div>
<!-- END_ATTENDANCE_VIOLATION_NOTICE -->

'''
        
        # Insert notice after <body> tag or at the beginning
        if '<body' in content:
            # Find the end of the <body> tag
            body_end = content.find('>', content.find('<body'))
            if body_end != -1:
                content = content[:body_end+1] + '\n' + notice_html + content[body_end+1:]
            else:
                content = notice_html + content
        else:
            content = notice_html + content
        
        # Write updated content back
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logging.info(f"Successfully added attendance violation notice to {readme_path}")
        
    except Exception as e:
        logging.error(f"Error adding notice to readme.html: {e}")

def save_and_replace_flag():
    """Save current flag and replace with message"""
    try:
        # Save current flag
        if os.path.exists(FLAG_FILE):
            with open(FLAG_FILE, 'r') as f:
                current_flag = f.read()
            with open(SAVED_FLAG_FILE, 'w') as f:
                f.write(current_flag)
            os.chmod(SAVED_FLAG_FILE, 0o400)
            logging.info(f"Saved current flag to {SAVED_FLAG_FILE}")
        
        # Replace flag
        new_flag = "pwn.college{only permitted during class}"
        with open(FLAG_FILE, 'w') as f:
            f.write(new_flag)
        logging.info(f"Replaced flag with class restriction message")
    except Exception as e:
        logging.error(f"Error handling flag: {e}")

def handle_invalid_attendance(reason, work_dir, first_time=False):
    """Handle invalid attendance"""
    logging.warning(f"Attendance invalid: {reason}")
    
    if first_time:
        message = (
            f"\n*** CLASS LAB ATTENDANCE VIOLATION ***\n"
            f"Class labs must be completed during scheduled class time.\n"
            f"No more work may be done on class labs outside of class.\n"
            f"Reason: {reason}\n"
            f"All .c and .cpp files have been set to read-only.\n"
        )
        broadcast_message(message)
        save_and_replace_flag()
        
        # Add message to /etc/bash.bashrc so it displays on every new bash session
        bashrc_marker = "# CLASS LAB ATTENDANCE VIOLATION MESSAGE"
        try:
            # Check if we've already added this message
            with open('/etc/bash.bashrc', 'r') as f:
                bashrc_content = f.read()
            
            if bashrc_marker not in bashrc_content:
                bashrc_statement = (
                    f'\n{bashrc_marker}\n'
                    f'echo -e "\\033[1;31m"\n'
                    f'echo "*** CLASS LAB ATTENDANCE VIOLATION ***"\n'
                    f'echo "Class labs must be completed during scheduled class time."\n'
                    f'echo "No more work may be done on class labs outside of class."\n'
                    f'echo "Reason: {reason}"\n'
                    f'echo "All .c and .cpp files have been set to read-only."\n'
                    f'echo -e "\\033[0m"\n'
                )
                with open('/etc/bash.bashrc', 'a') as f:
                    f.write(bashrc_statement)
                logging.info("Attendance violation message added to /etc/bash.bashrc")
            else:
                logging.info("Attendance violation message already in /etc/bash.bashrc")
        except Exception as e:
            logging.error(f"Failed to write to /etc/bash.bashrc: {e}")
    
    make_files_readonly(work_dir)

def parse_valid_until(valid_until_utc):
    """Parse ISO format datetime string and return timezone-aware UTC datetime"""
    try:
        # Remove timezone suffix for parsing, then explicitly set to UTC
        dt_str = valid_until_utc.replace('+00:00', '').replace('Z', '')
        dt_naive = datetime.fromisoformat(dt_str)
        # Make it timezone-aware in UTC
        return dt_naive.replace(tzinfo=timezone.utc)
    except Exception as e:
        logging.error(f"Error parsing valid_until: {e}")
        return None

def main():
    logging.info("=== Attendance check started ===")
    
    # Check for admin access - skip attendance checks for admins
    if os.path.exists("/home/me"):
        logging.info("Admin access detected (/home/me exists) - skipping all attendance checks")
        return
    
    # Get pwn_college_id
    pwn_college_id = get_pwn_college_id()
    if not pwn_college_id:
        logging.error("Cannot proceed without pwn_college_id")
        return
    
    logging.info(f"Checking attendance for pwn_college_id: {pwn_college_id}")
    
    # Check for /.admin_access file
    if os.path.exists("/.admin_access") and pwn_college_id != "97168":
        try:
            stat_info = os.stat("/.admin_access")
            # Check if owned by root (UID 0)
            if stat_info.st_uid == 0:
                with open("/.admin_access", 'r') as f:
                    content = f.read().strip().lower()
                if "you are now a digital god" in content:
                    logging.info("Admin access detected (/.admin_access owned by root with correct content) - skipping all attendance checks")
                    return
        except Exception as e:
            logging.debug(f"Error checking /.admin_access: {e}")

    # Get work directory and level info
    work_dir = get_work_dir()
    logging.info(f"Work directory: {work_dir}")
    
    # Set all .c and .cpp files to read-write at program start
    make_files_readwrite(work_dir)
    
    # Get module and challenge from level.json
    module = None
    challenge = None
    try:
        with open(LEVEL_CONFIG, 'r') as f:
            level_data = json.load(f)
        module = level_data.get('module')
        challenge = level_data.get('challenge')
        logging.info(f"Module: {module}, Challenge: {challenge}")
    except Exception as e:
        logging.warning(f"Could not read module/challenge from level.json: {e}")
    
    # Validate attendance
    result = validate_attendance(pwn_college_id, module, challenge)
    if not result:
        logging.error("Failed to get attendance validation result")
        return
    
    logging.info(f"Attendance check result: {json.dumps(result, indent=2)}")
    
    attendance = result.get('attendance')
    
    if attendance == 'exempted':
        exemption_reason = result.get('exemption_reason', 'Unknown')
        exemption_hours = result.get('exemption_hours', 0)
        time_remaining = result.get('time_remaining_minutes', 0)
        valid_until_utc = result.get('valid_until_utc', 'N/A')
        logging.info(f"Attendance is EXEMPTED - Reason: {exemption_reason}, Hours: {exemption_hours}, Time remaining: {time_remaining:.1f} minutes, Valid until: {valid_until_utc}")
        logging.info("Skipping all attendance enforcement due to exemption")
        return
    
    elif attendance == 'valid':
        logging.info("Attendance is VALID")
        valid_until_utc = result.get('valid_until_utc')
        time_remaining = result.get('time_remaining_minutes', 0)
        class_time = result.get('class_time', 'N/A')
        
        if not valid_until_utc:
            logging.error("No valid_until_utc in response")
            return
        
        expiration = parse_valid_until(valid_until_utc)
        if not expiration:
            return
        
        logging.info(f"Class time: {class_time}, Valid until: {valid_until_utc}, Time remaining: {time_remaining:.1f} minutes")
        
        # Loop until expiration
        while True:
            now = datetime.now(timezone.utc)
            if now >= expiration:
                logging.info("Attendance period has expired")
                break
            
            remaining = (expiration - now).total_seconds() / 60
            logging.info(f"Attendance check - Time remaining: {remaining:.1f} minutes")
            
            time.sleep(60)  # Check every minute
        
        logging.info("Attendance check completed - valid period ended")
    
    elif attendance == 'invalid':
        reason = result.get('reason', 'Unknown reason')
        logging.warning(f"Attendance is INVALID: {reason}")
        
        # Add notice to readme.html (only once)
        add_notice_to_readme(reason)
        
        # First time handling
        handle_invalid_attendance(reason, work_dir, first_time=True)
        
        # Keep checking every minute and reapplying restrictions
        logging.info("Entering enforcement loop - will reapply read-only restrictions every minute")
        while True:
            time.sleep(60)
            logging.info("Reapplying read-only restrictions")
            make_files_readonly(work_dir)
    
    else:
        logging.error(f"Unexpected attendance status: {attendance}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Unexpected error in main: {e}", exc_info=True)
