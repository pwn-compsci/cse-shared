#!/usr/bin/env python3
"""
Standalone script to report exam attempts to the API.
This runs independently of the Flask app for better reliability.
"""

import json
import os
import time
import requests
import re
import logging
from datetime import datetime

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

def report_exam_attempt():
    """Main function to report exam attempt to API with retry logic"""
    logger = setup_logger()
    max_attempts = 3
    retry_delay = 5  # seconds between attempts
    
    try:
        logger.info("Starting exam attempt reporter script")
        
        # Read level configuration
        level_config_path = '/challenge/.config/level.json'
        if not os.path.exists(level_config_path):
            logger.info(f"Level config file not found: {level_config_path}")
            return False
            
        with open(level_config_path, 'r') as f:
            level_config = json.load(f)
            
        module = level_config.get('module')
        challenge = level_config.get('level')
        
        if not module or not challenge:
            logger.info(f"Missing module or level in config. module={module}, level={challenge}")
            return False
            
        logger.info(f"Read config: module={module}, challenge={challenge}")
        
        # Get PWN College ID
        pwn_id = get_pwn_college_id()
        if not pwn_id:
            logger.info("Could not get PWN College ID")
            return False
            
        logger.info(f"Got PWN College ID: {pwn_id}")
        
        # Prepare payload
        payload = {
            'pwn_college_id': pwn_id,
            'module': module,
            'challenge': challenge
        }
        
        logger.info(f"Prepared payload for API: {payload}")
        
        # Make POST request with retry logic
        api_url = 'https://api.cse545.com/attempt_exam'
        
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Attempt {attempt}/{max_attempts}: Sending request to {api_url}")
                
                response = requests.post(api_url, json=payload, timeout=30)
                
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
