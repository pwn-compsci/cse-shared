#!/usr/bin/python3

import ipaddress
import os
import time
import random
import socket
import socketserver
import subprocess
import multiprocessing
import enum
import signal
import ctypes
import pathlib
import argparse
import json
import sys

import scapy.all as scapy

libc = ctypes.CDLL("libc.so.6")

def check_capabilities():
    """Check if we have the necessary capabilities for network operations"""
    try:
        # Try to create a raw socket to test NET_RAW capability
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        test_socket.close()
        return True
    except PermissionError:
        return False

def ensure_privileges():
    """Ensure we have the necessary privileges to run network challenges"""
    if not check_capabilities():
        print("Error: This script requires network capabilities (CAP_NET_RAW, CAP_NET_ADMIN)")
        print("Please run with:")
        print("1. Root privileges, or")
        print("2. Using landrun with --unrestricted-network, or") 
        print("3. Set file capabilities: sudo setcap 'cap_net_raw,cap_net_admin+ep' /usr/bin/python3")
        sys.exit(1)

# Check privileges early
ensure_privileges()

# Your existing code continues here...
flag = open("/flag").read()
parser = argparse.ArgumentParser(description="Set the challenge level.")

# Rest of your existing script...
