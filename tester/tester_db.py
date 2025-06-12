#!/usr/bin/env python3

import sqlite3
from pathlib import Path
from datetime import datetime
import json
import os
import re
import glob
import traceback 

# pylint: disable=line-too-long
# pylint: disable=unspecified-encoding
# pylint: disable=missing-function-docstring

VSCODE_HISTORY_DIR = "/home/hacker/.local/share/code-server/User/History/"

# SQLite database
BASE_HOME_DIR = "/home/hacker"
BASE_CSE240_DIR = f"{BASE_HOME_DIR}/cse240"
DATABASE = f'{BASE_CSE240_DIR}/.vscode/trdb.db'


def save_results(source_dir, passed, failed, initial_files, module_id, level_id, last_test_json_fp=None, flag=None):
    test_result_id = save_test_results(source_dir, passed, failed, module_id, level_id, last_test_json_fp)
    save_history_files(source_dir, initial_files, module_id, level_id, test_result_id)
    save_flag(flag, module_id, level_id)

def init_db(second_try=False):
    # if os.path.exists(DATABASE):
    #     return
    if DATABASE is None:
        return
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        c.execute('''CREATE TABLE IF NOT EXISTS tests
                        (id INTEGER PRIMARY KEY, module TEXT, level TEXT, timestamp TEXT,
                        passed INTEGER, failed INTEGER, code_change INTEGER, test_case_failed TEXT,
                        number_execs_before_test INTEGER, error_message Text, last_test_json_fp TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS history_files
                        (id INTEGER, module TEXT, level TEXT, timestamp TEXT,
                        abs_source_fp TEXT, relative_source_fp TEXT,
                        most_recent_histfile_path TEXT, most_recent_histfile_size TEXT,
                        number_of_history_files INTEGER, fk_test_id INTEGER, entries_fp TEXT,
                        PRIMARY KEY (id, relative_source_fp));
                ''')

        c.execute('''CREATE TABLE IF NOT EXISTS flags (id TEXT PRIMARY KEY, module TEXT, level TEXT, timestamp TEXT); ''')

        # Check if the column 'last_test_json_fp' exists in the 'tests' table
        # c.execute("PRAGMA table_info(tests)")
        # columns = [column[1] for column in c.fetchall()]
        # if 'last_test_json_fp' not in columns:
        #     c.execute("ALTER TABLE tests ADD COLUMN last_test_json_fp TEXT")

        # root has write, other has read
        os.chmod(DATABASE, 0o644)
        c.close()
        conn.commit()
        conn.close()
    except Exception as ex:
        if second_try == False:
            # Try to create the directory and try again
            os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            os.rename(DATABASE, DATABASE + f".{timestamp}.old")
            init_db(second_try=True)
        else:
            print(f"Error in init_db: {ex}")
            traceback.print_exc()
            raise ex 



def save_flag(flag, module_id, level_id):
    if DATABASE is None:
        return
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            INSERT INTO flags (id, module, level, timestamp)
            VALUES (?, ?, ?, ?)
        """
        c.execute(sql, (flag, module_id, level_id, timestamp))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"Error in save_flag: {e}")
        return


def save_history_files(source_dir, initial_files, module_id, level_id, test_result_id):
    if DATABASE is None:
        return
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()

        if initial_files is None:
            if os.path.exists(os.path.join(source_dir, "main.cpp")):
                initial_files = ["main.cpp"]
            elif os.path.exists(os.path.join(source_dir, "main.c")):
                initial_files = ["main.c"]
            else:
                initial_files = []

        sql = """
            INSERT INTO history_files
            (id, module, level, timestamp, abs_source_fp, relative_source_fp,
                most_recent_histfile_path, most_recent_histfile_size, number_of_history_files,
                fk_test_id, entries_fp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        adjustment = 0
        now = datetime.now()
        for file in initial_files:
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
            rowid = int(now.timestamp() * 1000) + adjustment
            adjustment += 10
            abs_source_fp, relative_source_fp, entries_fp, history_entries = get_history_files(source_dir, file, module_id, level_id)

            most_recent_histfile_path = history_entries[-1].get("file") if history_entries else None
            most_recent_histfile_size = os.path.getsize(most_recent_histfile_path) if most_recent_histfile_path else 0

            c.execute(sql, (rowid, module_id, level_id, timestamp, str(abs_source_fp), str(relative_source_fp),
                            str(most_recent_histfile_path), most_recent_histfile_size, len(history_entries),
                            test_result_id, str(entries_fp)))

        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        print(f"Error in save_history_file: {e}")
        traceback.print_exc()
        


def get_history_files(source_dir, file, module_id, level_id):
    full_path = os.path.join(source_dir, file)
    prefix_to_remove = os.path.abspath(os.path.join(source_dir, os.pardir, os.pardir))
    relative_path = os.path.normpath(full_path.replace(prefix_to_remove, ''))
    match = re.search(r'(\/[0-9]{2}-.*\/[0-9]{2}/.*)', full_path)
    if match:
        relative_path =  os.path.normpath(match.group(1))  # Return the matched group, which is the path from "/05-" onward
    entries_fp, entries = find_entries_json_with_file(relative_path, module_id, level_id)

    if entries_fp is None:
        return full_path, relative_path, "", []

    hist_dir = os.path.dirname(entries_fp)

    sorted_entries = sorted(entries, key=lambda entry: entry['timestamp'])

    history_entries = []
    for entry in sorted_entries:
        hist_file = entry.get('id')
        timestamp = entry.get('timestamp')
        hist_full_fp = os.path.join(hist_dir, hist_file)
        if os.path.exists(hist_full_fp):
            history_entries.append({"hist_file": hist_file, "timestamp": timestamp, "hist_full_fp": hist_full_fp})

    return full_path, relative_path, entries_fp, history_entries


def get_history_directory(file_path, module, level):
    try:
        if DATABASE is None:
            return None
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        sql = """
            SELECT entries_fp FROM history_files
            WHERE relative_source_fp = ? AND module = ? AND level = ?
        """
        c.execute(sql, (file_path, module, level))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None
    except sqlite3.Error as e:
        print(f"Error in get_history_directory: {e}")
        return None


def find_entries_json_with_file(file_path, module, level):
    entries_file = get_history_directory(file_path, module, level)
    # Search for entries.json files under all subdirectories of vscode_history_dir
    if entries_file is not None and os.path.exists(entries_file):
        with open(entries_file, 'r') as f:
            data = json.load(f)
        return entries_file, data.get("entries",[])

    for root, _, files in os.walk(VSCODE_HISTORY_DIR):
        if "entries.json" in files:
            entries_file = Path(root) / "entries.json"
            # Open the entries.json file and look for the file_path within its entries
            try:
                with open(entries_file, 'r') as f:
                    data = json.load(f)
                res = data.get("resource", "")
                if res.endswith(file_path):
                    # Check if any entry matches the file_path
                    return entries_file, data.get("entries",[])
            except Exception as e:
                print(f"Error reading {entries_file}: {e}")
                continue
    return None, None


def save_test_results(source_dir, passed, failed, module_id, level_id, last_test_json_fp, error_message = ""):
    try:
        if DATABASE is None:
            return None
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            INSERT INTO tests (id, module, level, timestamp, passed, failed, code_change, test_case_failed, number_execs_before_test, error_message, last_test_json_fp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        row_id = int(now.timestamp() * 1000)
        # timestamp = datetime.fromtimestamp(id / 1000.0).strftime("%Y-%m-%d %H:%M:%S")
        test_case_failed = failed > 0
        gcov_files = glob.glob(os.path.join(source_dir, "main.gcda"))
        number_execs_before_test = 0
        for gcov_file in gcov_files:
            with open(gcov_file, 'rb') as f:
                f.seek(24)  # Skip to the execution count
                exec_count = int.from_bytes(f.read(4), byteorder='little')
            number_execs_before_test += exec_count
        
        code_change = 0 # TODO
        c.execute(sql, (row_id, module_id, level_id, timestamp, passed, failed, code_change, test_case_failed, number_execs_before_test, error_message, last_test_json_fp))
        conn.commit()
        conn.close()
        return row_id
    except sqlite3.Error as e:
        print(f"Error in save_test_result: {e}")
        traceback.print_exc()
        return None
