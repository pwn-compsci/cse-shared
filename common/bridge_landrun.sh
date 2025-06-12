#!/bin/bash
CMD_FIFO="/run/landrun-cmd.fifo"
RESP_FIFO="/run/landrun-resp.fifo"
RESULT="/run/landrun-response.txt"

# Setup FIFOs if missing
[[ -p "$CMD_FIFO" ]] || mkfifo "$CMD_FIFO" && chmod 666 "$CMD_FIFO"
[[ -p "$RESP_FIFO" ]] || mkfifo "$RESP_FIFO" && chmod 666 "$RESP_FIFO"
touch "$RESULT" && chmod 666 "$RESULT"

echo "[+] Privileged listener running..."

while true; do
    echo "[+] Listening for command ..."
    if read -r command < "$CMD_FIFO"; then
        echo "[+] Received command: $command"

        if [[ "$command" == "run" ]]; then
            /challenge/tester > "$RESULT" 2>&1
            echo "OK" > "$RESP_FIFO"
        else
            echo "ERR" > "$RESP_FIFO"
        fi
    fi
done