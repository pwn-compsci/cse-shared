#!/bin/bash

course_code=${course_code:-$(jq -r '.course_code // "cse240"' /challenge/.config/level.json 2>/dev/null || echo cse240)}
course_home=${course_home:-"/home/hacker/$course_code"}
course_env_file=${course_env_file:-"$course_home/.${course_code}env"}

# Read the log file path created by .init
if [ -f /tmp/.startup_log_path ]; then
    STARTUP_LOG=$(cat /tmp/.startup_log_path)
else
    # Fallback if .init hasn't run yet
    STARTUP_LOG="$course_home/.vscode/logs/startup-$(date +%Y%m%d-%H%M%S).log"
    mkdir -p "$course_home/.vscode/logs"
fi

echo "[c] Attempting to start code-server..." >> $STARTUP_LOG

root_mutation_log() {
  local message="$1"
  if [ -n "${STARTUP_LOG:-}" ]; then
    echo "[guard] $message" >> "$STARTUP_LOG" 2>/dev/null || true
  else
    echo "[guard] $message" >&2
  fi
}

path_has_symlink_component() {
  local path="${1%/}"
  local probe=""
  local part=""

  [ -n "$path" ] || return 1
  case "$path" in
    /home/hacker|/home/hacker/*) ;;
    *) [ -L "$path" ] && return 0; return 1 ;;
  esac

  path="/${path#/}"
  IFS='/' read -r -a parts <<< "${path#/}"
  for part in "${parts[@]}"; do
    [ -n "$part" ] || continue
    probe="${probe}/${part}"
    if [ -L "$probe" ]; then
      root_mutation_log "blocked root mutation through symlink: $probe -> $(readlink "$probe" 2>/dev/null || echo unknown) while handling $1"
      return 0
    fi
    [ -e "$probe" ] || break
  done
  return 1
}

safe_root_mutation_path() {
  path_has_symlink_component "$1" && return 1
  return 0
}

safe_root_mutation_tree() {
  local path="$1"
  local link=""
  safe_root_mutation_path "$path" || return 1
  if [ -d "$path" ]; then
    link=$(find "$path" -type l -print -quit 2>/dev/null)
    if [ -n "$link" ]; then
      root_mutation_log "blocked root mutation in tree containing symlink: $link -> $(readlink "$link" 2>/dev/null || echo unknown)"
      return 1
    fi
  fi
  return 0
}

safe_chown() {
  local seen_owner=false
  local arg
  for arg in "$@"; do
    [ -n "$arg" ] || continue
    if [ "$seen_owner" = false ]; then
      [[ "$arg" == -* ]] && continue
      seen_owner=true
      continue
    fi
    [[ "$arg" == -* ]] && continue
    safe_root_mutation_path "$arg" || return 1
  done
  command chown "$@"
}

safe_chmod() {
  local seen_mode=false
  local arg
  for arg in "$@"; do
    [ -n "$arg" ] || continue
    [[ "$arg" == -* ]] && continue
    if [ "$seen_mode" = false ]; then
      seen_mode=true
      continue
    fi
    safe_root_mutation_path "$arg" || return 1
  done
  command chmod "$@"
}

safe_touch() {
  local arg
  for arg in "$@"; do
    [ -n "$arg" ] || continue
    [[ "$arg" == -* ]] && continue
    safe_root_mutation_path "$arg" || return 1
  done
  command touch "$@"
}

safe_mkdir_p() {
  local args=()
  local arg
  for arg in "$@"; do
    [ -n "$arg" ] || continue
    if [[ "$arg" == -* ]]; then
      args+=("$arg")
      continue
    fi
    safe_root_mutation_path "$arg" || return 1
    args+=("$arg")
  done
  command mkdir -p "${args[@]}"
}

until [ -f /run/dojo/var/ready ]; do sleep 0.1; done

if [ -d /run/challenge/share/code/extensions ]; then
  EXTENSIONS_DIR="/run/challenge/share/code/extensions"
else
  EXTENSIONS_DIR="/nix/store/5b5cpsjwl6y8qbpypl5kgfdv8cab5zbw-code-service/share/code/extensions"
fi

prepare_landrun_paths() {
  # landrun refuses missing paths listed in any access rule.
  safe_mkdir_p \
    /home/hacker/.cache \
    /home/hacker/.local/share/ultima \
    "$(dirname "$coder_workspace_file")" \
    "$(dirname "$course_env_file")" \
    "$course_home/.vscode" \
    "$clevel_work_dir" \
    "$code_server_data_dir" \
    "$cs_user_data_dir" \
    /run
  safe_touch \
    "$coder_workspace_file" \
    "$course_env_file" \
    /home/hacker/.bashrc \
    /home/hacker/.profile \
    /home/hacker/.bash_history \
    /.admin_access \
    /.user_info
  [[ -p /run/landrun-cmd.fifo ]] || { rm -f /run/landrun-cmd.fifo; mkfifo /run/landrun-cmd.fifo; }
  safe_chmod 666 /run/landrun-cmd.fifo
  safe_chown -R hacker:hacker \
    /home/hacker/.cache \
    /home/hacker/.local \
    "$course_home" \
    "$course_home/.vscode" \
    "$course_env_file" \
    "$clevel_work_dir" \
    "$cs_user_data_dir" \
    /home/hacker/.profile \
    /home/hacker/.bash_history \
    /home/hacker/.bashrc
  safe_chmod 664 "$course_env_file" /home/hacker/.bashrc /home/hacker/.profile /home/hacker/.bash_history
}

attempts=0
max_attempts=5

clevel_work_dir=$1
cs_user_data_dir=$2
coder_workspace_file=$3

if [ -z "$clevel_work_dir" ] || [ -z "$cs_user_data_dir" ] || [ -z "$coder_workspace_file" ]; then
  echo "[c] ERROR: Missing required parameters" >> $STARTUP_LOG
  exit 1
fi

code_server_data_dir="${cs_user_data_dir%/}/"

prepare_landrun_paths

# Ensure code-service directory exists with correct ownership
mkdir -p /run/dojo/var/code-service
safe_chown hacker:hacker /run/dojo/var/code-service
safe_chmod 755 /run/dojo/var/code-service
echo "[c] Created /run/dojo/var/code-service with hacker ownership" >> $STARTUP_LOG

# Clean up any existing code-server processes
if ps -ef | grep -q "/code-server/"; then
    echo "[c] Code-server already running - cleaning up" >> $STARTUP_LOG
    pkill -f "/code-server/" || true
    rm -f /run/dojo/var/code-service/code-server.pid || true
    mv /run/dojo/var/code-service/code-server.log /challenge/old_code-server.log 2>/dev/null || true 
fi

while [ $attempts -lt $max_attempts ]; do
  echo "[c] Start attempt $((attempts + 1))/$max_attempts" >> $STARTUP_LOG
  
  cmd=$(printf "
    /run/dojo/bin/landrun 
      --best-effort --add-exec --unrestricted-network -env PATH --env HOME 
      --rox /bin,/lib,/nix,/lib64,/opt,/sys,/usr,/sbin,/etc
      --rwx /proc
      --rox /.admin_access
      --rw /run/landrun-cmd.fifo 
      --ro  $coder_workspace_file,/.user_info
      --rw /home/hacker/.cache,/home/hacker/.local/
      --rw $cs_user_data_dir,/home/hacker/.local/share/ultima/ 
      --rw /home/hacker/.bashrc,$course_home/.vscode,$course_env_file,/home/hacker/.profile,/etc/bash.bashrc,/home/hacker/.bash_history
      --rwx $clevel_work_dir
      --rwx /dev/null,/dev/ptmx,/dev/pts,/dev/tty,/dev/urandom,/dev/random 
      --rwx /tmp 
      --rwx /run
      --rwx /challenge
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
  
  echo "[c] Command: $cmd" >> $STARTUP_LOG
  
  # Ensure PATH includes necessary directories
  export PATH="/run/challenge/bin:/run/dojo/bin:$PATH:/challenge/"
  
  # Write command to temp file to avoid quoting issues
  safe_root_mutation_path /tmp/vscode-cmd.sh && echo "$cmd" > /tmp/vscode-cmd.sh
  safe_chmod +x /tmp/vscode-cmd.sh
  
  # Execute as hacker user
  output=$(runuser -u hacker -- /tmp/vscode-cmd.sh 2>&1 | tee -a /challenge/vscode.log) 
  res=$?
  
  echo "[c] Exit code: $res" >> $STARTUP_LOG
  
  # Verify PID file was created
  if [ -f /run/dojo/var/code-service/code-server.pid ]; then
      pid=$(cat /run/dojo/var/code-service/code-server.pid 2>/dev/null)
      echo "[c] PID file created: $pid" >> $STARTUP_LOG
      ps -p "$pid" > /dev/null 2>&1 || echo "[c] WARNING: Process $pid not running" >> $STARTUP_LOG
  else
      echo "[c] WARNING: PID file not created" >> $STARTUP_LOG
  fi
  
  # Log any code-server output
  if [ -n "$output" ]; then
    echo "[c] Output: $output" >> $STARTUP_LOG
  fi
  
  # Check if already running error occurred
  if echo "$output" | grep -q "already running"; then
    echo "[c] Code-server already running - retrying..." >> $STARTUP_LOG
    attempts=$((attempts + 1))
    pkill -9 -f "/code-server/" || true
    rm -f /run/dojo/var/code-service/code-server.pid || true
    
    # Wait for process to die
    for i in {1..10}; do
      pgrep -f "/code-server/" > /dev/null || break
      sleep 1
    done
    
    sleep 1
    continue
  fi
  
  sleep .3

  # Verify process started
  success=0
  for i in {1..5}; do
    if pgrep -f "/code-server/" > /dev/null; then
      echo "[c] Process verified running" >> $STARTUP_LOG
      success=1
      break
    fi
    sleep 1
  done

  if [ $res -eq 0 ] && [ $success -eq 1 ]; then
    echo "[c] Code-server started successfully" >> $STARTUP_LOG
    break
  else
    echo "[c] Start failed" >> $STARTUP_LOG
    if [ -f /run/dojo/var/code-service/code-server.log ]; then 
      cat /run/dojo/var/code-service/code-server.log >> $STARTUP_LOG
    fi
    attempts=$((attempts + 1))
    sleep $((1 * attempts))
  fi

done

# Wait for HTTP server to respond
if pgrep -f "/code-server/"; then
  for i in {1..10}; do
    if /run/dojo/bin/curl -s localhost:4200 >/dev/null; then
      echo "[c] Code-server ready on port 4200 (attempt $i)" >> $STARTUP_LOG
      echo "[c] User data: $code_server_data_dir | Extensions: $EXTENSIONS_DIR" >> $STARTUP_LOG
      echo "[c] Logs: /run/dojo/var/code-service/code-server.log" >> $STARTUP_LOG
      break
    fi
    echo "[c] Waiting for HTTP response on port 4200... ($i/10)" >> $STARTUP_LOG
    sleep 1
  done
  echo "[c] Code-server log available at: /run/dojo/var/code-service/code-server.log" >> $STARTUP_LOG
else
  echo "[c] ERROR: Failed to start code-server after $max_attempts attempts" >> $STARTUP_LOG
fi
