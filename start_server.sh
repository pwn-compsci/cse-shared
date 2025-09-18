#!/bin/bash
"""
Startup script for the command server
Usage: ./start_server.sh [port]
"""

# Default port
PORT=${1:-1040}

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script should be run as root for full functionality"
   echo "Run with: sudo $0 $*"
fi

# Create log directory if it doesn't exist
mkdir -p /var/log

echo "Starting Command Server on port $PORT..."
echo "Press Ctrl+C to stop"
echo "Logs will be written to /var/log/cserver.log"

# Start the server
python3 /cse/cse-shared/common/cserver.py --port "$PORT"