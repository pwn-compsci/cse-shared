#!/usr/bin/python3

import logging

import glob
import os
import time

logging.basicConfig(
    filename="/var/log/broadcaster.log",
    filemode="a",
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO
)

FIFO_PATH = "/run/landrun-resp.fifo"

def broadcast_message(message):
    for tty in glob.glob("/dev/pts/[0-9]*"):
        try:
            with open(tty, "w") as f:
                f.write(message)
            logging.info(f"Broadcasted to {tty}: {message.strip()}")
        except Exception as e:
            logging.info(f"Failed to write to {tty}: {e}")

def main():
    # Ensure the FIFO exists
    if not os.path.exists(FIFO_PATH):
        logging.info(f"FIFO {FIFO_PATH} does not exist. Waiting for it to appear...")
        while not os.path.exists(FIFO_PATH):
            time.sleep(5)

    logging.info(f"Listening for commands in {FIFO_PATH}...")
    while True:
        with open(FIFO_PATH, "r") as fifo:
            for line in fifo:
                line = line.strip()
                if "pwn" in line:
                    logging.info(f"Received command with 'pwn': {line}")
                    broadcast_message("\n\n" + line + "\n\n")
                else:
                    logging.info(f"Ignoring command: {line}")

if __name__ == "__main__":
    main()
