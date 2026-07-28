#!/bin/bash

# restart_nginx.sh - Script to restart nginx with a delay
# Usage: restart_nginx.sh <nginx_conf_path>

NGINX_CONF_PATH="$1"
LOG_FILE="/var/log/nginx_restart.log"

# Function to log with timestamp
log_message() {
    echo "$(date): $1" | tee -a "$LOG_FILE"
}

if [ -z "$NGINX_CONF_PATH" ]; then
    log_message "Error: nginx configuration path not provided"
    log_message "Usage: $0 <nginx_conf_path>"
    exit 1
fi

if [ ! -f "$NGINX_CONF_PATH" ]; then
    log_message "Error: nginx configuration file not found: $NGINX_CONF_PATH"
    exit 1
fi

log_message "Starting nginx restart process..."

# Wait 1 second before proceeding
log_message "Waiting 1 second before restart..."
sleep 1

# Kill existing nginx processes
log_message "Killing existing nginx processes..."
pkill -f "nginx -c" 2>>"$LOG_FILE"
KILL_EXIT_CODE=$?
log_message "Kill command exit code: $KILL_EXIT_CODE"

# Wait a moment for processes to terminate
log_message "Waiting for processes to terminate..."
sleep 1

# Start nginx with the specific command used in Docker
log_message "Starting nginx with config: $NGINX_CONF_PATH"
nginx -c "$NGINX_CONF_PATH" >>"$LOG_FILE" 2>&1
START_EXIT_CODE=$?

if [ $START_EXIT_CODE -eq 0 ]; then
    log_message "Nginx started successfully"
else
    log_message "Error: Nginx failed to start (exit code: $START_EXIT_CODE)"
fi

log_message "Nginx restart process completed"
exit $START_EXIT_CODE
