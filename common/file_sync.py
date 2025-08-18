#! /usr/bin/env python3
import json
import os
import glob
import logging
import requests
import time
from time import sleep
import hashlib # for the sha256
import zipfile # for zipping the files
from zipfile import ZipFile
import base64 # for hashing the zip contents
import traceback

CSE240_DIR = '/home/hacker/cse240/'
DATABASE = f'{CSE240_DIR}/.vscode/trdb.db'
 
import sqlite3

def init_db():
    """
    Initializes the database
    """
    try:
        conn = sqlite3.connect(DATABASE)
        executor = conn.cursor()
        executor.execute('''CREATE TABLE IF NOT EXISTS latestFiles (id INTEGER PRIMARY KEY, module TEXT, level TEXT, filename TEXT, sha256 TEXT);''')

        os.chmod(DATABASE, 0o644)
        executor.close()
        conn.commit()
        conn.close()
    except Exception as ex:
        log.info(f"Error in init_db: {ex}")
        traceback.print_exc()
        raise ex

def query_for_sha256(module, level, filename):
    """
    Ensures that there is only one row for the passed in module, level, and filename
    
    Args:
        module (str): Module Identifier, will be inserted.
        level (str): Level Identifier, will be inserted.
        filename (str): The filename that will be inserted

    Returns:
        1. The stored sha256 if there is one row
        2. False if no rows
        3. None if error
    """
    try:
        conn = sqlite3.connect(DATABASE)
        executor = conn.cursor()
        sql = """ 
            SELECT sha256 FROM latestFiles 
            WHERE module = ? AND level = ? AND filename = ?
        """

        executor.execute(sql, (module, level, filename))
        result = executor.fetchone()
        conn.close()
        if result:
            return result[0]
        
        return False # has zero rows.
    except sqlite3.Error as e:
        log.info(f"Error in query_for_sha256: {e}")
        return None

def store_file(module, level, filename, sha256):
    """
    Used to store the file into the database.
    
    Args:
        module (str): Module Identifier, will be inserted.
        level (str): Level Identifier, will be inserted.
        filename (str): The filename that will be inserted
        sha256 (str): The sha256 hash that will be inserted.
    
    Returns: nothing
    """
    try:
        conn = sqlite3.connect(DATABASE)
        executor = conn.cursor()
        sql = """ 
            INSERT INTO latestFiles (module, level, filename, sha256)
            VALUES (?, ?, ?, ?)
        """

        executor.execute(sql, (module, level, filename, sha256))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        log.info(f"Error in store_file: {e}")
        return

def update_row(module, level, filename, sha256):
    """
    Updates the sha256 row based on module, level, and filename.
    
    Args:
        module (str): Module Identifier.
        level (str): Level Identifier.
        filename (str): The filename of the row that needs to be updated
        sha256 (str): The sha256 hash that will be updated.    
    """
    try:
        conn = sqlite3.connect(DATABASE)
        executor = conn.cursor()
        sql = """
            UPDATE latestFiles 
            SET sha256 = ?
            WHERE module = ? AND level = ? and filename = ?
        """

        executor.execute(sql, (sha256, module, level, filename))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        log.info(f"Error in update_row: {e}")
        return

# Setup logging
def setup_logging():
    """
    Set up logging to write to /var/log/sync.log
    """
    try:

        log_handler = logging.FileHandler('/var/log/sync.log')
        log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        log_handler.setFormatter(log_formatter)
        
        logger = logging.getLogger('sync')
        logger.setLevel(logging.INFO)
        logger.addHandler(log_handler)
        
        return logger
    except PermissionError:
        print("Error: Permission denied when trying to write to /var/log/sync.log")
        # Fall back to a temporary log file
        temp_handler = logging.FileHandler('/tmp/sync.log')
        temp_handler.setFormatter(log_formatter)
        logger.addHandler(temp_handler)
        logger.warning("Logging to /tmp/sync.log due to permission issues")
        return logger
    except Exception as e:
        print(f"Error setting up logging: {str(e)}")
        return None

def ensure_api_host_entry():
    """
    Ensures that 'api.cse545.com' is present in /etc/hosts.
    If not, adds '206.206.192.179   api.cse545.com' to the end of the file.
    """
    hosts_path = '/etc/hosts'
    entry = '206.206.192.179   api.cse545.com'
    try:
        with open(hosts_path, 'r') as f:
            lines = f.readlines()
        if any('api.cse545.com' in line for line in lines):
            log.info("'api.cse545.com' already present in /etc/hosts")
            return
        with open(hosts_path, 'a') as f:
            f.write('\n' + entry + '\n')
        log.info("Added 'api.cse545.com' entry to /etc/hosts")
    except PermissionError:
        log.error("Permission denied: cannot modify /etc/hosts")
    except Exception as e:
        log.error(f"Error updating /etc/hosts: {str(e)}")
        pass

def read_level_config():
    """
    Opens /challenge/.config/level.json and reads the JSON data into a variable.
    
    Returns:
        dict: The parsed JSON data from the level configuration file.
    """
    try:
        with open('/challenge/.config/level.json', 'r') as f:
            config_data = json.load(f)
        return config_data
    except FileNotFoundError:
        log.info("Error: Config file not found at /challenge/.config/level.json")
        return {}
    except json.JSONDecodeError:
        log.info("Error: Invalid JSON format in config file")
        return {}
    except Exception as e:
        log.info(f"Error reading config file: {str(e)}")
        return {}

def get_all_files(directory):
    """
    Find all the .c, .cpp, .h, .rkt, .pl files in the provided directory and return a list of the files name that has been modified in the past 2 minutes.
    
    Args:
        directory (str): Path to the directory to search in.
        
    Returns:
        list: filename of all the files in the provided directory, or None if no files found.
    """
    try:
        # Ensure directory exists
        if not os.path.isdir(directory):
            log.info(f"Error: Directory '{directory}' does not exist")
            return None
        
        # Get all .c, .cpp, .h, .rkt, and .pl files
        c_files = glob.glob(os.path.join(directory, "*.c"))
        cpp_files = glob.glob(os.path.join(directory, "*.cpp"))
        h_files = glob.glob(os.path.join(directory, "*.h"))
        rkt_files = glob.glob(os.path.join(directory, "*.rkt"))
        pl_files = glob.glob(os.path.join(directory, "*.pl"))
        all_files = c_files + cpp_files + h_files + rkt_files + pl_files
        
        threshold = time.time() - 120 # The current time - 2 minutes ago.

        if not all_files:
            log.info(f"No .c, .cpp, .h, .rkt, or .pl files found in '{directory}'")
            return None
            
        return [file for file in all_files if os.path.getmtime(file) >= threshold]
        
    except Exception as e:
        log.info(f"Error finding most recent script: {str(e)}")
        return None

def extract_pwn_college_id():
    """
    Extracts the pwn_college_id from /.user_info file
    
    Returns:
        str: The pwn_college_id value, or None if not found
    """
    try:
        with open('/.user_info', 'r') as file:
            for line in file:
                if line.startswith('pwn_college_id='):
                    # Extract the ID from the line in the format pwn_college_id='$pwn_college_id'
                    # Split by single quote to get the value between quotes
                    parts = line.strip().split("'")
                    if len(parts) >= 2:
                        return parts[1]
        # If we got here, we didn't find the ID
        log.info("Error: pwn_college_id not found in /.user_info")
        return None
    except FileNotFoundError:
        log.info("Error: /.user_info file not found")
        return None
    except Exception as e:
        log.info(f"Error reading /.user_info file: {str(e)}")
        return None

def sync_to_server(filename, content, module, level, pwn_college_id, isZipped):
    """
    Sends the file content, module, level, pwn_college_id, and isZipped to the sync API
    
    Args:
        filename (str): Name of the script file
        content (str): Content of the script file
        module (str): Module identifier
        level (str): Level identifier
        pwn_college_id (str): PWN College user ID
        isZipped (bool): If the passed in filename is a zip file, this value will be true, else false.
        
    Returns:
        bool: True if sync was successful, False otherwise
    """
    ensure_api_host_entry()  # Ensure the API host entry is present

    if not all([filename, content, module, level, pwn_college_id]):
        log.error("Missing required data for sync")
        return False
        
    try:
        url = "https://api.cse545.com/codesync"
        
        payload = {
            'filename': filename,
            'content': content,
            'module': module,
            'level': level,
            'pwn_college_id': pwn_college_id,
            'isZipped': isZipped
        }
        
        log.info(f"Syncing {filename} for {module}/{level} to server...")
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            log.info("Sync successful")
            return True
        else:
            log.error(f"Sync failed with status code: {response.status_code}")
            log.error(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        log.error(f"Request error: {str(e)}")
        return False
    except Exception as e:
        log.error(f"Error during sync: {str(e)}")
        return False

def computeSHA256(filename):
    """
    Computes the SHA256 of the passed in file.
    
    Args:
        filename (str): The file name that will be used to compute the SHA256
    
    Returns:
        The sha256sum of the file contents
    """
    h = hashlib.sha256()

    with open(filename, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    """
    Main function that reads the level configuration and controls the flow of the file sync.
    """
    #sleep(5)

    config = read_level_config()
    if config:
        module = config.get('module', 'module_unknown')
        hw = config.get('hw', 'hw_unknown')
        level = config.get('level', 'level_unknown')
        hwdir = config.get('hwdir', 'hwdir_unknown')
        
        # Adds the current directory to a list so it can look at a subdirectories (for pokemud or bfs)
        workdir = [os.path.join(hwdir, level)] 

        if module == "33-pokemud":
            workdir.append(os.path.join(hwdir, level, "pokemud"))
        if module == '33-muddydriver':
            workdir.append(os.path.join(hwdir, level, "muddydriver"))
        
        log.info(f"Module: {module}, Level: {level}, Workdir: {workdir}")
        while True:
            try:
                fileList = []
                for directories in workdir:
                    lstOfFiles = get_all_files(directories)
                    if lstOfFiles is not None:
                        fileList += lstOfFiles
                
                syncTheseFiles = []
                
                for file in fileList:
                    fullFilePath = file
                    baseFileName = os.path.basename(file)
                    shaHash = computeSHA256(baseFileName)
                    databaseSha = query_for_sha256(module, level, baseFileName)
                    
                    if databaseSha == shaHash:
                        continue # goes to the next file in fileList
                    elif databaseSha is False: # Store the file if not in database.
                        store_file(module, level, baseFileName, shaHash) 
                    elif databaseSha != shaHash: # Update the sha256 in the database. 
                        update_row(module, level, baseFileName, shaHash)
                    
                    syncTheseFiles.append(fullFilePath)

                pwn_college_id = extract_pwn_college_id()
                
                if len(syncTheseFiles) == 1:
                    file_contents = ""
                    with open(syncTheseFiles[0], "r") as f:
                        file_contents = f.read()
                    sync_result = sync_to_server(os.path.basename(syncTheseFiles[0]), file_contents, module, level, pwn_college_id, False)
                    
                elif len(syncTheseFiles) > 1:
                    zipName = f'{pwn_college_id}_{module}_{level}.zip'
                    with ZipFile(zipName, 'w') as zip:
                        for file in syncTheseFiles:
                            zip.write(os.path.basename(file))
                    
                    zip_contents = ""
                    with open(zipName, 'rb') as zip:
                        zip_contents = zip.read()

                    zip_encoded = base64.b64encode(zip_contents).decode('utf-8')
                    sync_result = sync_to_server(zipName, zip_encoded, module, level, pwn_college_id, True)

                    os.remove(f'{pwn_college_id}_{module}_{level}.zip') # deletes the zip file.
                
                individal_send = ["compile.log", "tester.log"]

                for indiv_file in individal_send:
                    if os.path.isfile(indiv_file) and os.path.getmtime(indiv_file) >= (time.time() - 120): # If the file has been modified in the past 2 minutes, execute the if statement.
                        file_contents = ""
                        with open(indiv_file, "r") as f:
                            file_contents = f.read()
                        sync_result = sync_to_server(indiv_file.replace(".", ""), file_contents, module, level, pwn_college_id, False)

                sleep(60)
            except Exception as e:
                log.error(f"Error during main loop: {str(e)}")
        
    else:
        log.info("No configuration data available.")

if __name__ == "__main__":
    log = setup_logging()
    init_db()
    main()