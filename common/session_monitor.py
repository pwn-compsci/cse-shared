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
API_URL = "https://api.cse545.com/session_times"
CHECK_INTERVAL = 60  # Check every 60 seconds
MAX_RETRIES = 3
RETRY_DELAY = 5  # Seconds between retries

def get_current_utc_time():
    """Get current time in UTC"""
    return datetime.now(timezone.utc)

def fetch_session_times():
    """
    Fetch session times from the API
    
    Returns:
        dict: Session data or None if failed
    """
    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Fetching session times from {API_URL} (attempt {attempt + 1}/{MAX_RETRIES})")
            
            response = requests.get(API_URL, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"API Response: {json.dumps(data, indent=2)}")
            
            if data.get('status') == 'success' and data.get('session_found'):
                return data
            elif data.get('status') == 'success' and not data.get('session_found'):
                logger.warning("No current session found")
                return None
            else:
                logger.error(f"API returned error: {data.get('message', 'Unknown error')}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                time.sleep(RETRY_DELAY)
            else:
                logger.error("All retry attempts failed")
                return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None
    
    return None

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

def check_exam_attendance():
    """
    Extract pwn_college_id from /.user_info and check exam attendance status
    
    Returns:
        bool: True if attending exam, False otherwise, None if error
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
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"Exam attendance API response: {json.dumps(data, indent=2)}")
            
            # Return the attending status
            attending = data.get('attending', False)
            logger.info(f"Exam attendance status: {attending}")
            return attending
            
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


def mark_session_terminated():
    """
    Terminate process ID 1, which will kill the script
    """
    # Check for user id 132329 in /.user_info
    try:
        with open('/.user_info', 'r') as f:
            user_info = f.read()        
    except Exception as e:
        logger.error(f"Error reading /.user_info: {e}")
    
    try:
        with open(SESSION_FILE, 'w') as f:
            f.write("terminated\n")
        os.chown(SESSION_FILE, 0, 0)
        os.chmod(SESSION_FILE, 0o600)
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
        os.chmod(SESSION_FILE, 0o600)
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

def main():
    """Main monitoring loop"""
    logger.info("Session Monitor starting...")
    logger.info(f"Process ID: {os.getpid()}")
    logger.info(f"Parent Process ID: {os.getppid()}")
    logger.info(f"Current UTC time: {get_current_utc_time().isoformat()}")
    
    # Initial session check
    session_data = fetch_session_times()
    
    if session_data:
        start_time_str = session_data.get('start_time_utc')
        end_time_str = session_data.get('end_time_utc')
        start_time = parse_iso_datetime(start_time_str)
        end_time = parse_iso_datetime(end_time_str)
        if not start_time or not end_time:
            logger.critical("Failed to parse session times - terminating")
            mark_session_terminated()
            return
    else:
        default_minutes = 120
        logger.info(f"Using default_session_time: {default_minutes} minutes")
        start_time = get_current_utc_time()
        end_time = start_time + timedelta(minutes=default_minutes)            

    
    logger.info(f"Session found: {session_data['type']}")
    logger.info(f"Session start (UTC): {start_time.isoformat()}")
    logger.info(f"Session end (UTC): {end_time.isoformat()}")
    
    # Check if we're currently within the session
    current_time = get_current_utc_time()
    if not is_time_in_session(current_time, start_time, end_time):
        logger.critical("Current time is outside session window - terminating")
        mark_session_terminated()
        return
    
    logger.info("Session is active - entering monitoring loop")
    mark_session_active()

    missing_attendance = 0
    # Main monitoring loop
    try:
        while True:
            time.sleep(CHECK_INTERVAL)
            
            current_time = get_current_utc_time()
            logger.info(f"Checking session status at {current_time.isoformat()}")
            
            # Check if session has ended
            if current_time > end_time:
                logger.critical("Session has ended - terminating")
                mark_session_terminated()
                continue 
            
            # Check if we're still within the session window
            if not is_time_in_session(current_time, start_time, end_time):
                logger.critical("Current time is outside session window - terminating")
                mark_session_terminated()
                continue 
            
            # Calculate time remaining
            time_remaining = end_time - current_time
            minutes_remaining = int(time_remaining.total_seconds() / 60)
            logger.info(f"Session is active - {minutes_remaining} minutes remaining")

            check_results = check_exam_attendance()
            if check_results is None :
                missing_attendance += 1
                if missing_attendance >= 3:
                    logger.critical("Multiple attempts to detect attendance failed, terminating session")
                    broadcast_message("Multiple attempts to detect attendance failed, you will no longer be able to get the flag from running\n")
                    mark_session_terminated()
                    continue
            elif check_results == True:
                mark_session_active()
                missing_attendance = 0
            else:
                logger.critical("Exam attendance check failed - terminating")
                broadcast_message("You are no longer shown as logged into the exam, please contact course staff.\nYou will no longer be able to get the flag from the tester")
                mark_session_terminated()
                continue

    except KeyboardInterrupt:
        logger.info("Received interrupt signal - exiting gracefully")
    except Exception as e:
        logger.error(f"Unexpected error in monitoring loop: {e}")
        #kill_process_1()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        #kill_process_1()
