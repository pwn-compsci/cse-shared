#!/bin/bash
CMD_FIFO="/run/landrun-cmd.fifo"
RESP_FIFO="/run/landrun-resp.fifo"
RESULT="/run/landrun-response.txt"

# Setup FIFOs if missing
[[ -p "$CMD_FIFO" ]] || mkfifo "$CMD_FIFO" && chmod 666 "$CMD_FIFO"
[[ -p "$RESP_FIFO" ]] || mkfifo "$RESP_FIFO" && chmod 666 "$RESP_FIFO"
touch "$RESULT" && chmod 666 "$RESULT"
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "[+] Privileged listener running..."

while true; do
    log "[+] Listening for command ..."
    if read -r command < "$CMD_FIFO"; then
        log "[+] Received command: $command"

        if [[ "$command" == "run" ]]; then
            log "[+] Starting the tester script sending results to $RESULT"
            /challenge/tester > "$RESULT" 2>&1
            echo "OK" > "$RESP_FIFO"
        else
            echo "ERR" > "$RESP_FIFO"
        fi
    fi
done