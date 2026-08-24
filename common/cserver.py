#!/usr/bin/env python3
"""
Command Server - A long-running process that receives connections and executes commands
Runs as root and listens on a configurable port (default 1040)
"""

import socket
import threading
import subprocess
import sys
import os
import argparse
import logging
import shutil
from typing import Optional

# Configure logging
def setup_logging():
    handlers = [logging.StreamHandler(sys.stdout)]
    
    # Try to add file handler if we have write permissions
    try:
        handlers.append(logging.FileHandler('/var/log/cserver.log'))
    except PermissionError:
        # Fall back to local log file if /var/log is not writable
        try:
            handlers.append(logging.FileHandler('./cserver.log'))
        except PermissionError:
            pass  # Just use console logging
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

setup_logging()
logger = logging.getLogger(__name__)

def find_tester_command() -> Optional[str]:
    search_path = os.pathsep.join([
        os.environ.get("PATH", ""),
        "/run/challenge/bin",
        "/challenge/bin",
        "/challenge",
    ])
    return shutil.which("tester", path=search_path)

class CommandServer:
    def __init__(self, port: int = 1040, host: str = '0.0.0.0'):
        self.port = port
        self.host = host
        self.socket = None
        self.running = False
        
    def start(self):
        """Start the server and begin listening for connections"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            self.running = True
            
            logger.info(f"Command server started on {self.host}:{self.port}")
            logger.info(f"Running as user: {os.getuid()}")
            
            while self.running:
                try:
                    client_socket, client_address = self.socket.accept()
                    logger.info(f"Connection from {client_address}")
                    
                    # Handle each client in a separate thread
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except socket.error as e:
                    if self.running:
                        logger.error(f"Socket error: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            sys.exit(1)
    
    def handle_client(self, client_socket: socket.socket, client_address: tuple):
        """Handle communication with a connected client - closes after processing single line"""
        try:
            with client_socket:
                # Send welcome message
                welcome_msg = "Command Server Ready. Send commands followed by newline.\n"
                client_socket.send(welcome_msg.encode('utf-8'))
                
                # Read exactly one line and process it
                client_file = client_socket.makefile('r', encoding='utf-8')
                line = client_file.readline().strip()
                
                if line:
                    logger.info(f"Received command from {client_address}: {line}")
                    
                    # Process the single command
                    response = self.process_command(line)
                    
                    # Send response back to client
                    if response:
                        client_socket.send(response.encode('utf-8'))
                    
                    # Send end-of-response marker
                    client_socket.send(b"\n--- END OF RESPONSE ---\n")
                    
                    logger.info(f"Processed command '{line}', closing connection to {client_address}")
                else:
                    logger.warning(f"Received empty command from {client_address}, closing connection")
                        
        except Exception as e:
            logger.error(f"Error handling client {client_address}: {e}")
        finally:
            logger.info(f"Client {client_address} disconnected")
    
    def process_command(self, command: str) -> str:
        """Process received command and return response"""
        command_parts = command.lower().split()
        
        if not command_parts:
            logger.warning("Received empty command")
            return "ERROR: Empty command\n"
        
        base_command = command_parts[0]
        logger.debug(f"Processing command: '{base_command}' (original: '{command}')")
        
        if base_command == "tester":
            return self.execute_tester()
        elif base_command == "kill":
            return self.execute_kill()
        elif base_command == "quit" or base_command == "exit":
            return "Goodbye\n"
        else:
            logger.warning(f"Unknown command received: '{base_command}' (original: '{command}')")
            return f"ERROR: Unknown command '{base_command}'. Available commands: tester, kill, quit, exit\n"
    
    def execute_tester(self) -> str:
        """Execute tester and return all output with ANSI encoding preserved"""
        try:
            tester_cmd = find_tester_command()
            logger.info("Executing tester")
            
            if not tester_cmd:
                error_msg = "ERROR: tester not found on PATH. Please ensure the tester command is available.\n"
                logger.error(error_msg.strip())
                return error_msg
            
            if not os.access(tester_cmd, os.X_OK):
                error_msg = f"ERROR: tester exists at {tester_cmd} but is not executable.\n"
                logger.error(error_msg.strip())
                return error_msg
            
            process = subprocess.Popen(
                [tester_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,  # Keep as bytes to preserve ANSI encoding
                cwd="/challenge"
            )
            
            stdout_data, stderr_data = process.communicate()
            
            # Decode with error handling to preserve ANSI sequences
            try:
                stdout_text = stdout_data.decode('utf-8', errors='replace')
            except UnicodeDecodeError:
                stdout_text = stdout_data.decode('latin1')
            
            try:
                stderr_text = stderr_data.decode('utf-8', errors='replace')
            except UnicodeDecodeError:
                stderr_text = stderr_data.decode('latin1')
            
            # Combine stdout and stderr, preserving order as much as possible
            result = ""
            if stdout_text:
                result += "STDOUT:\n" + stdout_text
            if stderr_text:
                result += "\nSTDERR:\n" + stderr_text
            
            result += f"\nEXIT CODE: {process.returncode}\n"
            
            logger.info(f"Tester execution completed with exit code: {process.returncode}")
            return result
            
        except Exception as e:
            error_msg = f"ERROR: Failed to execute tester: {str(e)}\n"
            logger.error(error_msg.strip())
            return error_msg
    
    def execute_kill(self) -> str:
        """Kill all main.bin processes with retry logic"""
        try:
            logger.info("Attempting to kill all main.bin processes")
            
            max_retries = 5
            retry_delay = 1
            signal = "TERM"
            attempt = 1
            killed_count = 0
            
            while attempt <= max_retries:
                # Find all main.bin processes using pgrep
                try:
                    pgrep_result = subprocess.run(
                        ["pgrep", "-f", "main\\.bin"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=5
                    )
                    
                    pids = pgrep_result.stdout.strip().split('\n') if pgrep_result.stdout.strip() else []
                    pids = [p for p in pids if p]  # Remove empty strings
                    
                except subprocess.TimeoutExpired:
                    logger.error("pgrep command timed out")
                    return "ERROR: pgrep command timed out\n"
                
                if not pids:
                    if attempt == 1:
                        logger.info("No main.bin processes found")
                        return "INFO: No main.bin processes found\n"
                    else:
                        logger.info(f"Successfully killed all {killed_count} main.bin process(es)")
                        return f"SUCCESS: Killed {killed_count} main.bin process(es)\n"
                
                count = len(pids)
                logger.warning(f"Attempt {attempt}/{max_retries}: Found {count} main.bin process(es)")
                
                if attempt == 1:
                    killed_count = count
                
                # Kill processes with current signal
                for pid in pids:
                    try:
                        subprocess.run(
                            ["kill", f"-{signal}", pid],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            timeout=5
                        )
                        logger.info(f"Sent {signal} to PID {pid}")
                    except subprocess.TimeoutExpired:
                        logger.error(f"kill command timed out for PID {pid}")
                    except Exception as e:
                        logger.error(f"Failed to kill PID {pid}: {e}")
                
                # Wait before checking if processes are still alive
                if attempt < max_retries:
                    logger.info(f"Waiting {retry_delay}s before retry...")
                    import time
                    time.sleep(retry_delay)
                
                # Escalate to SIGKILL on final attempt
                if attempt == max_retries - 1:
                    logger.warning("Final attempt will use SIGKILL")
                    signal = "KILL"
                
                attempt += 1
            
            # Final check
            try:
                final_check = subprocess.run(
                    ["pgrep", "-f", "main\\.bin"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5
                )
                remaining_pids = final_check.stdout.strip().split('\n') if final_check.stdout.strip() else []
                remaining_pids = [p for p in remaining_pids if p]
                
                if remaining_pids:
                    error_msg = f"ERROR: {len(remaining_pids)} main.bin process(es) still running after {max_retries} attempts: {', '.join(remaining_pids)}\n"
                    logger.error(error_msg.strip())
                    return error_msg
                else:
                    success_msg = f"SUCCESS: Successfully killed all {killed_count} main.bin process(es) after {attempt-1} attempt(s)\n"
                    logger.info(success_msg.strip())
                    return success_msg
                    
            except subprocess.TimeoutExpired:
                logger.error("Final pgrep check timed out")
                return "ERROR: Final process check timed out\n"
            
        except Exception as e:
            error_msg = f"ERROR: Failed to kill main.bin processes: {str(e)}\n"
            logger.error(error_msg.strip())
            return error_msg

    
    def stop(self):
        """Stop the server gracefully"""
        logger.info("Stopping command server...")
        self.running = False
        if self.socket:
            self.socket.close()

def main():
    parser = argparse.ArgumentParser(description="Command Server")
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=1040,
        help='Port to listen on (default: 1040)'
    )
    parser.add_argument(
        '--host',
        type=str,
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    
    args = parser.parse_args()
    
    # Check if running as root
    if os.getuid() != 0:
        logger.warning("Not running as root - some commands may fail")
    
    server = CommandServer(port=args.port, host=args.host)
    
    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        server.stop()

if __name__ == "__main__":
    main()
