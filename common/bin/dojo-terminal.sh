#!/bin/bash
echo "[t] Attempting to start VNC Desktop Connection..." 

# Wait for the system to be ready
until [ -f /run/dojo/var/ready ]; do sleep 0.1; done

old_path=$PATH
export PATH=$PATH:/run/dojo/bin

ttyd_bin=$(find /nix/store -maxdepth 4 -type f -path "*/bin/ttyd")

echo "[t] 1. $ttyd_bin " 
services='/run/dojo/bin'

export TERM=xterm-256color

prepare_landrun_paths() {
  # landrun refuses missing paths that are listed as writable.
  mkdir -p \
    /home/hacker/.cache \
    /home/hacker/.config \
    /home/hacker/.local/share/ultima \
    /home/hacker/cse545/.vscode \
    "$cs_user_data_dir"
  chown -R hacker:hacker \
    /home/hacker/.cache \
    /home/hacker/.config \
    /home/hacker/.local \
    /home/hacker/cse545/.vscode
}

prepare_landrun_paths

if pgrep -f "ttyd"; then
    ps -ef | grep -E "ttyd" 
    echo "[t] Dojo-terminal service are already running. Killing existing process before initial attempt" 
    pkill -9 -f "ttyd" || true
    printf "[t] checking after kill to see if running " 
    ps -ef | grep -E "ttyd" 
else
    echo "[t] No existing terminal processes found. Proceeding to start a new instance." 
fi

echo "[t] Starting up terminal service" 
cmd=$(printf "
    /usr/local/bin/landrun  
  --best-effort --add-exec --unrestricted-network -env PATH --env HOME=\"$clevel_work_dir\" --env MANPATH=/run/dojo/share/man:/usr/share/man
  --rox /bin,/lib,/run,/nix,/challenge,/lib64,/opt,/sys,/usr,/sbin,/etc 
  --rox /usr/bin/exec-suid,/usr/bin/python3,/usr/lib,/usr/sbin
  --ro /etc,/proc,/sys,/lib,/lib64 
  --ro /flag,/run/landrun-stdout.fifo,/run/landrun-resp.fifo,/run/landrun-stdout.fifo,/run/landrun-response.txt 
  --rwx /proc
  --rox /challenge,/.admin_access 
  --rw /run/landrun-cmd.fifo,/run/landrun-stdin.fifo
  --rw /home/hacker/.cache,/home/hacker/.local/,/home/hacker/.config 
  --rox /home/hacker/.ssh
  --rw /home/hacker/.local/share/ultima/ 
  --rw /home/hacker/cse545/.vscode,/home/hacker/.profile 
  --rw $cs_user_data_dir 
  --rwx $clevel_work_dir 
  --rwx /tmp,/var,/dev
  --rwx /run/dojo/var
  -- "$services/dojo-service" start terminal-service/ttyd 
     "$ttyd_bin" 
    --port 7682 
    --interface 0.0.0.0 
    --writable 
    -t disableLeaveAlert=true 
    $SHELL --login -c \"cd '$clevel_work_dir' && exec $SHELL --login\"
    " | tr -d "\n" |tr -s " ")

printf "[t] Running command:\n"
printf "$cmd\n\n" 
id 

#output=$(su - hacker -c "$cmd | tee -a /run/dojo/var/desktop-service/xfce4.log 2>&1")
eval "$cmd" 2>&1 | tee -a /run/dojo/var/terminal-service/terminal.log
EXIT_CODE=$?

sleep 0.2
if [ "$EXIT_CODE" -ne 0 ] || grep -q "landrun:error" /run/dojo/var/terminal-service/terminal.log; then
  echo "[t] Landrun failed with exit code $EXIT_CODE. Locking down port 7682..."
  pkill -9 -f "ttyd" || true
  sleep 0.2
  # Keep port blocked and send "Terminal error" via HTTP with white font
  while true; do
      { echo -e "HTTP/1.1 503 Service Unavailable\r\nContent-Type: text/html\r\n\r\n<span style=\"color:white;\">Terminal error</span>"; } | nc -l -p 7682 > /dev/null
  done &
  echo "[t] terminal port locked."
else
  echo "[t] Landrun succeeded with exit code $EXIT_CODE."
fi

until curl -fs localhost:7682 >/dev/null; do sleep 0.1; done

#cleanup
export PATH=$old_path
