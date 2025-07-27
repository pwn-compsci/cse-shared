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
import time
import signal
import requests
import json
from datetime import datetime, timezone
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/session_monitor.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

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
            
            response = requests.get(API_URL, timeout=10)
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

def kill_process_1():
    """
    Terminate process ID 1, which will kill the script
    """
    logger.critical("Terminating process ID 1 - script will exit")
    try:
        # Send SIGTERM to process 1
        os.kill(1, signal.SIGTERM)
        time.sleep(2)  # Give it a moment
        
        # If still running, send SIGKILL
        os.kill(1, signal.SIGKILL)
    except ProcessLookupError:
        logger.info("Process 1 already terminated")
    except PermissionError:
        logger.error("Permission denied - cannot kill process 1")
        # Fallback: exit the script
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to kill process 1: {e}")
        # Fallback: exit the script
        sys.exit(1)

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
    
    if not session_data:
        logger.critical("No valid session found at startup - terminating")
        kill_process_1()
        return
    
    # Parse session times
    start_time_str = session_data.get('start_time_utc')
    end_time_str = session_data.get('end_time_utc')
    
    if not start_time_str or not end_time_str:
        logger.critical("Missing session time data - terminating")
        kill_process_1()
        return
    
    start_time = parse_iso_datetime(start_time_str)
    end_time = parse_iso_datetime(end_time_str)
    
    if not start_time or not end_time:
        logger.critical("Failed to parse session times - terminating")
        kill_process_1()
        return
    
    logger.info(f"Session found: {session_data['type']}")
    logger.info(f"Session start (UTC): {start_time.isoformat()}")
    logger.info(f"Session end (UTC): {end_time.isoformat()}")
    
    # Check if we're currently within the session
    current_time = get_current_utc_time()
    if not is_time_in_session(current_time, start_time, end_time):
        logger.critical("Current time is outside session window - terminating")
        kill_process_1()
        return
    
    logger.info("Session is active - entering monitoring loop")
    
    # Main monitoring loop
    try:
        while True:
            time.sleep(CHECK_INTERVAL)
            
            current_time = get_current_utc_time()
            logger.info(f"Checking session status at {current_time.isoformat()}")
            
            # Check if session has ended
            if current_time > end_time:
                logger.critical("Session has ended - terminating")
                kill_process_1()
                break
            
            # Check if we're still within the session window
            if not is_time_in_session(current_time, start_time, end_time):
                logger.critical("Current time is outside session window - terminating")
                kill_process_1()
                break
            
            # Calculate time remaining
            time_remaining = end_time - current_time
            minutes_remaining = int(time_remaining.total_seconds() / 60)
            logger.info(f"Session is active - {minutes_remaining} minutes remaining")
            
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
