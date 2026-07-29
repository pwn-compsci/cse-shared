#!/usr/bin/env python3
"""
Standalone script to report exam attempts to the API.
This runs independently of the Flask app for better reliability.
Waits for /opt/exam_attempt_startup_id to exist before reporting.
"""

import json
import os
import time
import requests
import re
import logging
import stat
from datetime import datetime

API_TOKEN = "08b26e01b8d9cb4f262da37836912504104296c33ab658dca836d032bc47b2ff"

def setup_logger():
    """Setup logger to write to /challenge/startup.log"""
    logger = logging.getLogger('exam_reporter')
    logger.setLevel(logging.INFO)
    
    # Remove any existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # File handler for /challenge/startup.log
    file_handler = logging.FileHandler('/challenge/startup.log', mode='a')
    file_handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s'))
    logger.addHandler(file_handler)
    
    # Prevent propagation to root logger (no console output)
    logger.propagate = False
    
    return logger

def get_pwn_college_id():
    """Read PWN College ID from /.user_info file"""
    try:
        with open('/.user_info', 'r') as f:
            content = f.read()
            # Look for pwn_college_id='value' pattern
            match = re.search(r"pwn_college_id='(\d+)'", content)
            if match:
                return match.group(1)
    except Exception as e:
        return None
    return None

def wait_for_startup_id_file(logger, timeout=300):
    """Wait for the root-created startup UUID and return it."""
    startup_id_path = '/opt/exam_attempt_startup_id'
    start_time = time.time()

    logger.info(f"Waiting for {startup_id_path} to exist and contain a UUID...")

    while time.time() - start_time < timeout:
        try:
            if os.path.exists(startup_id_path):
                file_stat = os.stat(startup_id_path)
                if file_stat.st_uid != 0:
                    logger.info(f"{startup_id_path} exists but is not owned by root (uid={file_stat.st_uid}), waiting...")
                else:
                    with open(startup_id_path, 'r') as f:
                        startup_id = f.read().strip()
                    if startup_id:
                        logger.info(f"Using startup_id from {startup_id_path}: {startup_id}")
                        return startup_id
                    logger.info(f"{startup_id_path} exists but is empty, waiting...")
        except Exception as e:
            logger.info(f"Error reading {startup_id_path}: {e}, waiting...")

        time.sleep(2)

    logger.info(f"Timeout waiting for {startup_id_path} after {timeout} seconds")
    return None

def report_exam_attempt():
    """Main function to report exam attempt to API with retry logic"""
    logger = setup_logger()
    max_attempts = 3
    retry_delay = 5  # seconds between attempts
    
    try:
        logger.info("Starting exam attempt reporter script (background mode)")
        
        logger.info("Proceeding with exam attempt report after startup")
        
        # Read level configuration
        level_config_path = '/challenge/.config/level.json'
        if not os.path.exists(level_config_path):
            logger.info(f"Level config file not found: {level_config_path}")
            return False
            
        with open(level_config_path, 'r') as f:
            level_config = json.load(f)
            
        module = level_config.get('module')
        challenge = level_config.get('challenge') or level_config.get('examLevel')
        
        if not module or not challenge:
            logger.info(f"Missing module or examLevel in config. module={module}, examLevel={challenge}")
            return False
            
        logger.info(f"Read config: module={module}, challenge={challenge}")
        
        # Get PWN College ID
        pwn_id = get_pwn_college_id()
        if not pwn_id:
            logger.info("Could not get PWN College ID")
            return False
            
        logger.info(f"Got PWN College ID: {pwn_id}")
        startup_id = wait_for_startup_id_file(logger)
        if not startup_id:
            logger.info("Failed to get startup_id file, cannot report exam attempt")
            return False
        
        # Prepare payload
        payload = {
            'pwn_college_id': pwn_id,
            'module': module,
            'challenge': challenge,
            'startup_id': startup_id
        }
        
        logger.info(f"Prepared payload for API: {payload}")
        
        # Make POST request with retry logic
        api_url = 'https://api.cse545.com/attempt_exam'
        
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Attempt {attempt}/{max_attempts}: Sending request to {api_url}")
                
                response = requests.post(
                    api_url,
                    json=payload,
                    headers={'X-API-Token': API_TOKEN},
                    timeout=30
                )
                
                logger.info(f"Attempt {attempt} - API Response - Status: {response.status_code}, Body: {response.text}")
                
                if response.status_code == 200:
                    logger.info(f"Successfully reported exam attempt to API on attempt {attempt}")
                    return True  # Success
                else:
                    logger.info(f"Attempt {attempt} failed with status {response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                logger.info(f"Attempt {attempt} - Network error when contacting API: {e}")
            except Exception as e:
                logger.info(f"Attempt {attempt} - Unexpected error during API request: {e}")
            
            # If this wasn't the last attempt, wait before retrying
            if attempt < max_attempts:
                logger.info(f"Waiting {retry_delay} seconds before attempt {attempt + 1}")
                time.sleep(retry_delay)
        
        # If we get here, all attempts failed
        logger.info(f"All {max_attempts} attempts to contact API failed")
        return False
            
    except json.JSONDecodeError as e:
        logger.info(f"JSON decode error reading level config: {e}")
        return False
    except Exception as e:
        logger.info(f"Unexpected error in exam reporter: {e}")
        return False

if __name__ == '__main__':
    success = report_exam_attempt()
    exit(0 if success else 1)
