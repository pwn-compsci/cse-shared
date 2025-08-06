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
        """Override to suppress default logging (can be enabled if needed)"""
        pass  # Comment this line to enable request logging

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    print(f"\nReceived signal {signum}, shutting down server...")
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
            print(f"Redirect server running on port {port}")
            print(f"All requests will be redirected to: https://pwn.college/workspace/code")
            print("Press Ctrl+C to stop")
            
            # Serve forever (until interrupted)
            httpd.serve_forever()
            
    except PermissionError:
        print(f"Error: Permission denied to bind to port {port}")
        print("Try running with sudo or use a port > 1024")
        sys.exit(1)
    except OSError as e:
        if e.errno == 98:  # Address already in use
            print(f"Error: Port {port} is already in use")
            print("Another process may be using this port")
        else:
            print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nServer stopped by user")
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
        print(f"Fork failed: {e}")
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
        print(f"Second fork failed: {e}")
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
    
    args = parser.parse_args()
    
    if args.daemon:
        print(f"Starting redirect server as daemon on port {args.port}...")
        daemonize()
    
    run_server(args.port)

if __name__ == "__main__":
    main()
