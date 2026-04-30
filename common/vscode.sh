#!/bin/bash
set -x

# Read the log file path created by .init
if [ -f /tmp/.startup_log_path ]; then
    STARTUP_LOG=$(cat /tmp/.startup_log_path)
else
    # Fallback if .init hasn't run yet
    STARTUP_LOG="/home/hacker/cse240/.vscode/logs/startup-$(date +%Y%m%d-%H%M%S).log"
    mkdir -p /home/hacker/cse240/.vscode/logs
fi

echo "[c] Attempting to start code-server..." >> $STARTUP_LOG

until [ -f /run/dojo/var/ready ]; do sleep 0.1; done

if [ -d /run/challenge/share/code/extensions ]; then
  EXTENSIONS_DIR="/run/challenge/share/code/extensions"
else
  EXTENSIONS_DIR="/nix/store/5b5cpsjwl6y8qbpypl5kgfdv8cab5zbw-code-service/share/code/extensions"
fi
code_server_data_dir=/home/hacker/.local/share/code-server-exam/
if [ ! -d $code_server_data_dir ]; then
  mkdir -p $code_server_data_dir
  chown hacker:hacker $code_server_data_dir
fi

attempts=0
max_attempts=5

clevel_work_dir=$1
cs_user_data_dir=$2
coder_workspace_file=$3

if [ -z "$clevel_work_dir" ] || [ -z "$cs_user_data_dir" ] || [ -z "$coder_workspace_file" ]; then
  echo "[c] Error: One or more required parameters are missing." >> $STARTUP_LOG
  exit 1
fi

# Ensure the code-service directory exists before trying to interact with files in it
mkdir -p /run/dojo/var/code-service
echo "[c] Ensured /run/dojo/var/code-service directory exists" >> $STARTUP_LOG

if ps -ef | grep -q "/code-server/"; then
    echo "[c] Code-server is already running. Killing existing process before initial attempt" >> $STARTUP_LOG
    if [ -f /run/dojo/var/code-service/code-server.pid ]; then
        echo "[c] PID file exists before cleanup: $(cat /run/dojo/var/code-service/code-server.pid 2>/dev/null || echo 'cannot read')" >> $STARTUP_LOG
    else
        echo "[c] PID file does not exist before cleanup" >> $STARTUP_LOG
    fi
    pkill -f "/code-server/" || true
    rm -f /run/dojo/var/code-service/code-server.pid || true
    mv /run/dojo/var/code-service/code-server.log /challenge/old_code-server.log || true 
fi

while [ $attempts -lt $max_attempts ]; do
  echo "[c] Attempting to start code server." >> $STARTUP_LOG
  cmd=$(printf "
    landrun 
      --best-effort --add-exec --unrestricted-network -env PATH --env HOME 
      --rox /bin,/lib,/run,/nix,/challenge,/lib64,/opt,/sys,/usr,/sbin,/etc  
      --rwx /proc
      --rox /challenge,/.admin_access
      --rw /run/landrun-cmd.fifo 
      --ro  $coder_workspace_file,/.user_info
      --rw /home/hacker/.cache,/home/hacker/.local/
      --rw $cs_user_data_dir,/home/hacker/.local/share/ultima/ 
      --rw /home/hacker/.bashrc,/home/hacker/cse240/.vscode,/home/hacker/cse240/.cse240env,/home/hacker/.profile,/etc/bash.bashrc,/home/hacker/.bash_history
      --rwx $clevel_work_dir
      --rwx /dev/null,/dev/ptmx,/dev/pts,/dev/tty,/dev/urandom,/dev/random 
      --rwx /tmp 
      --rwx /run/dojo/var 
      -- /run/dojo/bin/dojo-service start code-service/code-server
          /run/dojo/bin/code-server
          --auth=none 
          --bind-addr=127.0.0.1:4200 
          --trusted-origins='*' 
          --disable-telemetry 
          --extensions-dir=$EXTENSIONS_DIR 
          --user-data-dir=$code_server_data_dir 
          --config=/dev/null
    " | tr -d "\n" |tr -s " ")
  
  echo "[c] Running command:" >> $STARTUP_LOG
  echo "$cmd" >> $STARTUP_LOG
  printf "\n**END**\n" >> $STARTUP_LOG
  
  echo "[c] About to execute command as hacker user" >> $STARTUP_LOG
  echo "[c] Current user running script: $(whoami)" >> $STARTUP_LOG
  echo "[c] Current PATH: $PATH" >> $STARTUP_LOG
  echo "[c] /challenge/vscode.log permissions: $(ls -l /challenge/vscode.log 2>&1)" >> $STARTUP_LOG
  echo "[c] Checking if /run/dojo/bin/dojo-service exists and is executable:" >> $STARTUP_LOG
  ls -l /run/dojo/bin/dojo-service >> $STARTUP_LOG 2>&1
  file /run/dojo/bin/dojo-service >> $STARTUP_LOG 2>&1
  echo "[c] Checking if landrun is available:" >> $STARTUP_LOG
  which landrun >> $STARTUP_LOG 2>&1 || echo "[c] landrun not found in PATH" >> $STARTUP_LOG
  ls -l /usr/bin/landrun >> $STARTUP_LOG 2>&1 || echo "[c] /usr/bin/landrun not found" >> $STARTUP_LOG
  echo "[c] Environment as hacker:" >> $STARTUP_LOG
  su - hacker -c "echo PATH=\$PATH; echo HOME=\$HOME; which landrun; which python3" >> $STARTUP_LOG 2>&1
  
  # this puts the output of the command in the log and also in the variable $output for checking if it contains "already running"  
  output=$(su - hacker -c "$cmd" 2>&1 | tee -a /challenge/vscode.log) 
  res=$?
  
  echo "[c] Command completed with exit code: $res" >> $STARTUP_LOG
  echo "[c] Output variable length: ${#output}" >> $STARTUP_LOG
  echo "[c] /challenge/vscode.log size: $(stat -c%s /challenge/vscode.log 2>&1)" >> $STARTUP_LOG
  
  
  if [ -f /run/dojo/var/code-service/code-server.log ]; then 
      echo "[c] After output execute command dumping /run/dojo/var/code-service/code-server.log" >> $STARTUP_LOG
      cat /run/dojo/var/code-service/code-server.log >> $STARTUP_LOG 2>/dev/null || true
      echo "---------------------------------------------------------------------------" >> $STARTUP_LOG
  else 
      echo "[c] /run/dojo/var/code-service/code-server.log does not exist after command execution." >> $STARTUP_LOG
  fi

  ps -ef | grep "/code-server/" >> $STARTUP_LOG

  if [ -z "$output" ]; then
    echo "[c] No output from code-server command." >> $STARTUP_LOG
  else
    echo "[c] Output of code-server command:" >> $STARTUP_LOG
    echo "$output" >> $STARTUP_LOG
    echo "----------------------------------------------------------------------------" >> $STARTUP_LOG
  fi  
  
  if echo "$output" | grep -q "already running"; then
    echo "[c] Code-server is already running. Killing existing process and retrying..." >> $STARTUP_LOG
    attempts=$((attempts + 1))
    if [ -f /run/dojo/var/code-service/code-server.pid ]; then
        echo "[c] PID file exists in retry loop: $(cat /run/dojo/var/code-service/code-server.pid 2>/dev/null || echo 'cannot read')" >> $STARTUP_LOG
    else
        echo "[c] PID file does not exist in retry loop" >> $STARTUP_LOG
    fi
    pkill -9 -f "/code-server/" || true
    rm -f /run/dojo/var/code-service/code-server.pid || true
    
    for i in {1..10}; do
      if ! pgrep -f "/code-server/" > /dev/null; then
        echo "[c] code-server process no longer running after $i seconds." >> $STARTUP_LOG
        break
      fi
      echo "[c] Checking if code-server is still running... ($i/10)" >> $STARTUP_LOG
      sleep 1
    done

    if [ -f /run/dojo/var/code-service/code-server.log ]; then 
      echo "[c] Dumping /run/dojo/var/code-service/code-server.log" >> $STARTUP_LOG
      cat /run/dojo/var/code-service/code-server.log >> $STARTUP_LOG 2>/dev/null || true
      echo "---------------------------------------------------------------------------" >> $STARTUP_LOG
    fi
    sleep 1
    echo "[c] Attempt #$((attempts + 1)) to start code-server again" >> $STARTUP_LOG
    continue
  fi
  
  sleep .3

  success=0
  for i in {1..5}; do
    if pgrep -f "/code-server/" > /dev/null; then
      echo "[c] code-server process detected after $i attempt(s)." >> $STARTUP_LOG
      success=1
      break
    fi
    echo "[c] Waiting for code-server process... ($i/5)" >> $STARTUP_LOG
    sleep 1
  done

  if [ $res -eq 0 ] && [ $success -eq 1 ]; then
    echo "[c] landrun and code-server command returned 0 and process is running." >> $STARTUP_LOG
    break
  else
    echo "[c] Failed to start code-server (attempt $((attempts + 1))/$max_attempts). Retrying..." >> $STARTUP_LOG
    if [ -f /run/dojo/var/code-service/code-server.log ]; then cat /run/dojo/var/code-service/code-server.log >> $STARTUP_LOG ; fi
    attempts=$((attempts + 1))
    sleep $((1 * attempts))
  fi

done # end of while loop

if pgrep -f "/code-server/"; then
  echo "[c] Waiting for code-server to start..." >> $STARTUP_LOG

  for i in {1..10}; do
    if /run/dojo/bin/curl -s localhost:4200 >/dev/null; then
      echo "[c] code-server responded on port 4200 after $i attempt(s)." >> $STARTUP_LOG
      echo "[c] Code-server is up and running with user data dir: $code_server_data_dir and extensions dir: $EXTENSIONS_DIR" >> $STARTUP_LOG
      break
    else
      echo "[c] Waiting for code-server to respond on port 4200... ($i/10)" >> $STARTUP_LOG
      sleep 1
    fi
  done
  echo "[c] Code-server log available at: /run/dojo/var/code-service/code-server.log" >> $STARTUP_LOG
else
  echo "[c] Failed to start code-server after $max_attempts attempts." >> $STARTUP_LOG
fi


