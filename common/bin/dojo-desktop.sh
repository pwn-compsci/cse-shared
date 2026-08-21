#!/bin/bash
echo "[d] Attempting to start VNC Desktop Connection..." 

# Wait for the system to be ready
until [ -f /run/dojo/var/ready ]; do sleep 0.1; done

> /tmp/found_paths #empty out old
old_path=$PATH
export PATH=$PATH:/run/dojo/bin
echo "[d] Machine ID(dojo-desktop): $(cat /etc/machine-id)" 

find /nix/store -maxdepth 4 -type f \( \
    -path "*/bin/openssl" -o \
    -path "*/bin/vncpasswd" -o \
    -name "Xvnc" -o \
    -name "novnc" -o \
    -name "xfce4-session" -o \
    -name "dbus-launch" -o \
    -path "*/share/dbus-1/session.conf" \
\) > /tmp/found_paths

openssl_path=$(grep "/bin/openssl" /tmp/found_paths | head -n 1)
vncpasswd_path=$(grep "/bin/vncpasswd" /tmp/found_paths | head -n 1)
tiger_xvnc_bin=$(grep "/Xvnc" /tmp/found_paths | head -n 1)
novnc_bin=$(grep "/novnc" /tmp/found_paths | head -n 1)
xfce_bin=$(grep "xfce4-session" /tmp/found_paths | head -n 1)
dbus_launch=$(grep "dbus-launch" /tmp/found_paths | head -n 1)
dbus_config=$(grep "session.conf" /tmp/found_paths | head -n 1)
echo "[d] 1. $openssl_path " 
echo "[d] 2. $vncpasswd_path " 
echo "[d] 3. $tiger_xvnc_bin " 
echo "[d] 4. $novnc_bin " 
echo "[d] 5. $xfce_bin " 
echo "[d] 6. $dbus_launch " 
echo "[d] 7. $dbus_config " 
services='/run/dojo/bin'


export DISPLAY=:0
export XDG_DATA_DIRS="/run/dojo/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
export XDG_CONFIG_DIRS="/run/dojo/etc/xdg:${XDG_CONFIG_DIRS:-/etc/xdg}"

echo "[d] setting up passwords" 
# Generate VNC passwords
auth_token="$(cat /run/dojo/var/auth_token)"
password_interact="$(printf 'desktop-interact' | "$openssl_path" dgst -sha256 -hmac "$auth_token" | awk '{print $2}' | head -c 8)"
password_view="$(printf 'desktop-view' | "$openssl_path" dgst -sha256 -hmac "$auth_token" | awk '{print $2}' | head -c 8)"

mkdir -p /run/dojo/var/desktop-service
printf '%s\n%s\n' "$password_interact" "$password_view" | "$vncpasswd_path" -f > /run/dojo/var/desktop-service/Xvnc.passwd

# Launch Xvnc (not sandboxed)
if pgrep -f "novnc|Xvnc|xfce4"; then
    ps -ef | grep -E "novnc|xfce4|Xvnc" 
    echo "[d] Dojo-desktop services are already running. Killing existing process before initial attempt" 
    pkill -9 -f "novnc|websockify|Xvnc|xfce4|xfconfd|dbus-launch" || true
    printf "[d] checking after kill to see if running " 
    ps -ef | grep -E "novnc|xfce4|Xvnc" 
else
    echo "[d] No existing desktop processes found. Proceeding to start a new instance." 
fi

echo "[d] Starting up tigervnc" 
"$services/dojo-service" start desktop-service/Xvnc \
     "$tiger_xvnc_bin" \
     $DISPLAY \
    -localhost 0 \
    -rfbunixpath /run/dojo/var/desktop-service/Xvnc.sock \
    -rfbauth /run/dojo/var/desktop-service/Xvnc.passwd \
    -nolisten tcp \
    -geometry 1024x768 \
    -depth 24 

echo "[d] starting up xvnc" 
# Launch noVNC (not sandboxed)
"$services/dojo-service" start desktop-service/novnc \
    "$novnc_bin" \
    --vnc --unix-target=/run/dojo/var/desktop-service/Xvnc.sock \
    --listen 6200 

# Wait for Xvnc and noVNC to be ready
until [ -e /tmp/.X11-unix/X0 ]; do sleep 0.1; done
until curl -s localhost:6200 >/dev/null; do sleep 0.1; done

# Launch xfce4-session inside a sandbox using landrun
echo "[d] cs_user_data_dir $cs_user_data_dir"
echo "[d] clevel_work_dir $clevel_work_dir"

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

if pgrep -f "xfce4"; then
    ps -ef | grep -E "xfce4" 
    echo "[d] Xfce4 session is already running. Killing existing process before initial attempt" 
    pkill -9 -f "xfce4|xfconfd|dbus-launch" || true
    printf "[d] checking after kill to see if running " 
    ps -ef | grep -E "novnc|xfce4|Xvnc" 
else
    echo "[d] No existing xfce4 session found. Proceeding to start a new session." 
fi

echo "[d] starting up xfce4" 
cmd=$(printf "
    /usr/local/bin/landrun  
  --best-effort --add-exec --unrestricted-network -env PATH --env HOME=\"$clevel_work_dir\" --env DISPLAY -env XDG_DATA_DIRS --env XDG_CONFIG_DIRS
  --env MANPATH=/run/dojo/share/man:/usr/share/man
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
  -- "$services/dojo-service" start desktop-service/xfce4-session 
    "$dbus_launch" --sh-syntax --exit-with-session --config-file=$dbus_config $xfce_bin
    " | tr -d "\n" |tr -s " ")

printf "[d] Running command:\n"
printf "$cmd\n\n" 
id 

#output=$(su - hacker -c "$cmd | tee -a /run/dojo/var/desktop-service/xfce4.log 2>&1")
eval "$cmd" 2>&1 | tee -a /run/dojo/var/desktop-service/xfce4.log
EXIT_CODE=$?

sleep 0.2
if [ "$EXIT_CODE" -ne 0 ] || grep -q "landrun:error" /run/dojo/var/desktop-service/xfce4.log; then
  echo "[d] Landrun failed with exit code $EXIT_CODE. Locking down port 6200..."
  pkill -9 -f "novnc|websockify|Xvnc|xfce4|xfconfd|dbus-launch" || true
  sleep 0.2
  # Keep port blocked and send "Desktop error" via HTTP with white font
  while true; do
      { echo -e "HTTP/1.1 503 Service Unavailable\r\nContent-Type: text/html\r\n\r\n<span style=\"color:white;\">Desktop error</span>"; } | nc -l -p 6200 > /dev/null
  done &
  echo "[d] novnc port locked."
else
  echo "[d] Landrun succeeded with exit code $EXIT_CODE."
fi

#cleanup
export PATH=$old_path
