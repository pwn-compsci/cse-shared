#!/bin/bash

echo "[c] Attempting to start code-server..." >> /challenge/startup.log

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
  echo "[c] Error: One or more required parameters are missing." >> /challenge/startup.log
  exit 1
fi

if ps -ef | grep -q "code-server"; then
    echo "[c] Code-server is already running. Killing existing process before initial attempt" >> /challenge/startup.log
    pkill -f code-server || true
    rm -f /run/dojo/var/code-service/code-server.log 
fi

while [ $attempts -lt $max_attempts ]; do
  echo "[c] Attempting to start code server." >> /challenge/startup.log
  cmd=$(printf "
    landrun 
      --best-effort --add-exec --unrestricted-network -env PATH --env HOME 
      --rox /bin,/lib,/run,/nix,/challenge,/lib64,/opt,/sys,/usr,/sbin,/etc  
      --rwx /proc
      --rox /challenge,/.admin_access
      --rw /run/landrun-cmd.fifo 
      --ro  $coder_workspace_file
      --rw /home/hacker/.cache,/home/hacker/.local/
      --rw $cs_user_data_dir,/home/hacker/.local/share/ultima/ 
      --rw /home/hacker/.bashrc,/home/hacker/cse240/.vscode,/home/hacker/cse240/.cse240env,/home/hacker/.profile,/etc/bash.bashrc
      --rwx $clevel_work_dir
      --rwx /dev/null,/dev/ptmx,/dev/pts,/dev/tty,/dev/urandom,/dev/random 
      --rwx /tmp 
      --rwx /run/dojo/var 
      -- /run/workspace/bin/dojo-service start code-service/code-server
          /run/workspace/bin/code-server
          --auth=none 
          --bind-addr=127.0.0.1:4200 
          --trusted-origins='*' 
          --disable-telemetry 
          --extensions-dir=$EXTENSIONS_DIR 
          --user-data-dir=$code_server_data_dir 
          --config=/dev/null
    " | tr -d "\n" |tr -s " ")
  
  echo "[c] Running command:" >> /challenge/startup.log
  echo "$cmd" >> /challenge/startup.log
  printf "\n**END**\n" >> /challenge/startup.log
  
  output=$(su - hacker -c "$cmd | tee -a /tmp/vscode.log 2>&1")
  res=$?
  
  cat /run/dojo/var/code-service/code-server.log >> /challenge/startup.log
  
  ps -ef | grep "code-server" >> /challenge/startup.log

  if [ -z "$output" ]; then
    echo "[c] No output from code-server command." >> /challenge/startup.log
  else
    echo "[c] Output of code-server command:" >> /challenge/startup.log
    echo "$output" >> /challenge/startup.log
    echo "----------------------------------------------------------------------------" >> /challenge/startup.log
  fi  
  
  if echo "$output" | grep -q "already running"; then
    echo "[c] Code-server is already running. Killing existing process and retrying..." >> /challenge/startup.log
    attempts=$((attempts + 1))
    pkill -9 -f code-server || true
    
    for i in {1..10}; do
      if ! pgrep -f "code-server" > /dev/null; then
        echo "[c] code-server process no longer running after $i seconds." >> /challenge/startup.log
        break
      fi
      echo "[c] Checking if code-server is still running... ($i/10)" >> /challenge/startup.log
      sleep 1
    done

    if [ -f /run/dojo/var/code-service/code-server.log ]; then 
      echo "[c] Dumping /run/dojo/var/code-service/code-server.log" >> /challenge/startup.log
      cat /run/dojo/var/code-service/code-server.log >> /challenge/startup.log ; 
      echo "---------------------------------------------------------------------------" >> /challenge/startup.log
    fi
    sleep 1
    echo "[c] Attempt #$((attempts + 1)) to start code-server again" >> /challenge/startup.log
    continue
  fi
  
  sleep .3

  success=0
  for i in {1..5}; do
    if pgrep -f "code-server" > /dev/null; then
      echo "[c] code-server process detected after $i attempt(s)." >> /challenge/startup.log
      success=1
      break
    fi
    echo "[c] Waiting for code-server process... ($i/5)" >> /challenge/startup.log
    sleep 1
  done

  if [ $res -eq 0 ] && [ $success -eq 1 ]; then
    echo "[c] landrun and code-server command returned 0 and process is running." >> /challenge/startup.log
    break
  else
    echo "[c] Failed to start code-server (attempt $((attempts + 1))/$max_attempts). Retrying..." >> /challenge/startup.log
    if [ -f /run/dojo/var/code-service/code-server.log ]; then cat /run/dojo/var/code-service/code-server.log >> /challenge/startup.log ; fi
    attempts=$((attempts + 1))
    sleep $((1 * attempts))
  fi

done # end of while loop

if pgrep -f "code-server"; then
  echo "[c] Waiting for code-server to start..." >> /challenge/startup.log

  for i in {1..10}; do
    if /run/workspace/bin/curl -s localhost:4200 >/dev/null; then
      echo "[c] code-server responded on port 4200 after $i attempt(s)." >> /challenge/startup.log
      echo "[c] Code-server is up and running with user data dir: $code_server_data_dir and extensions dir: $EXTENSIONS_DIR" >> /challenge/startup.log
      break
    else
      echo "[c] Waiting for code-server to respond on port 4200... ($i/10)" >> /challenge/startup.log
      sleep 1
    fi
  done
  echo "[c] Code-server log available at: /run/dojo/var/code-service/code-server.log" >> /challenge/startup.log
else
  echo "[c] Failed to start code-server after $max_attempts attempts." >> /challenge/startup.log
fi


