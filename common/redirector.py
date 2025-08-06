#!/usr/bin/env python3
"""
Background HTTP server that redirects all requests to https://pwn.college/workspace/code
Listens on port 7681
"""

import http.server
import socketserver
import sys
import signal
import os
import logging
from urllib.parse import urlparse

class RedirectHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler that redirects all requests to pwn.college workspace"""
    
    def do_GET(self):
        """Handle GET requests with 302 redirect"""
        self.send_response(302)
        self.send_header('Location', 'https://pwn.college/workspace/code')
        self.end_headers()
    
    def do_POST(self):
        """Handle POST requests with 302 redirect"""
        self.send_response(302)
        self.send_header('Location', 'https://pwn.college/workspace/code')
        self.end_headers()
    
    def do_HEAD(self):
        """Handle HEAD requests with 302 redirect"""
        self.send_response(302)
        self.send_header('Location', 'https://pwn.college/workspace/code')
        self.end_headers()
    
    def log_message(self, format, *args):
        """Log HTTP requests to the configured logger"""
        logging.info(f"{self.client_address[0]} - {format % args}")

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logging.info(f"Received signal {signum}, shutting down server...")
    sys.exit(0)

def run_server(port=7681):
    """Run the redirect server on specified port"""
    try:
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Create and configure the server
        with socketserver.TCPServer(("", port), RedirectHandler) as httpd:
            httpd.allow_reuse_address = True
            logging.info(f"Redirect server running on port {port}")
            logging.info(f"All requests will be redirected to: https://pwn.college/workspace/code")
            
            # Serve forever (until interrupted)
            httpd.serve_forever()
            
    except PermissionError:
        logging.error(f"Permission denied to bind to port {port}")
        logging.error("Try running with sudo or use a port > 1024")
        sys.exit(1)
    except OSError as e:
        if e.errno == 98:  # Address already in use
            logging.error(f"Port {port} is already in use")
            logging.error("Another process may be using this port")
        else:
            logging.error(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logging.info("Server stopped by user")
        sys.exit(0)

def daemonize():
    """Run the server as a background daemon process"""
    try:
        # First fork
        pid = os.fork()
        if pid > 0:
            # Parent process exits
            sys.exit(0)
    except OSError as e:
        logging.error(f"Fork failed: {e}")
        sys.exit(1)
    
    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)
    
    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            # Second parent exits
            sys.exit(0)
    except OSError as e:
        logging.error(f"Second fork failed: {e}")
        sys.exit(1)
    
    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    
    # Close stdin, stdout, stderr and redirect to /dev/null
    with open('/dev/null', 'r') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open('/dev/null', 'w') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())

def setup_logging(log_file='/var/log/redirector.log', is_daemon=False):
    """Configure logging for the application"""
    # Create log directory if it doesn't exist
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except PermissionError:
            # Fall back to local directory if can't write to /var/log
            log_file = './redirector.log'
    
    # Configure logging format
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Set up handlers
    handlers = []
    
    # Always add file handler
    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        handlers.append(file_handler)
    except PermissionError:
        # Fall back to local file if can't write to specified location
        local_log = './redirector.log'
        file_handler = logging.FileHandler(local_log)
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        handlers.append(file_handler)
    
    # Add console handler only if not running as daemon
    if not is_daemon:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(log_format, date_format))
        handlers.append(console_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        handlers=handlers,
        format=log_format,
        datefmt=date_format
    )

def main():
    """Main function to parse arguments and start server"""
    import argparse
    
    parser = argparse.ArgumentParser(description='HTTP redirect server for pwn.college workspace')
    parser.add_argument('-p', '--port', type=int, default=7681,
                       help='Port to listen on (default: 7681)')
    parser.add_argument('-d', '--daemon', action='store_true',
                       help='Run as background daemon')
    parser.add_argument('--foreground', action='store_true',
                       help='Run in foreground (default behavior)')
    parser.add_argument('--log-file', default='/var/log/redirector.log',
                       help='Log file path (default: /var/log/redirector.log)')
    
    args = parser.parse_args()
    
    # Set up logging before daemonizing
    setup_logging(args.log_file, args.daemon)
    
    if args.daemon:
        logging.info(f"Starting redirect server as daemon on port {args.port}...")
        daemonize()
        # Reconfigure logging after daemonizing (no console output)
        setup_logging(args.log_file, True)
    
    run_server(args.port)

if __name__ == "__main__":
    main()
