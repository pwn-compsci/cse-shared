#!/bin/bash
CMD_FIFO="/run/landrun-cmd.fifo"
RESP_FIFO="/run/landrun-resp.fifo"
RESULT="/run/landrun-response.txt"

# Check if cserver.py exists and is running
if [[ -f "/challenge/bin/cserver.py" ]] && pgrep -f "cserver.py" > /dev/null; then
    echo "[sandbox] Using cserver.py"
    printf "tester\n" | nc 0.0.0.0 1040
else
    # Send command
    echo "run" > "$CMD_FIFO"

    # Wait for response signal
    if read -r status < "$RESP_FIFO"; then
        if [[ "$status" == "OK" ]]; then
            echo "[sandbox] test results available at $RESULT"
            cat "$RESULT"
        else
            echo "[sandbox] Error: $status"
        fi
    else
        echo "[sandbox] No response from privileged listener."
    fi
fi
