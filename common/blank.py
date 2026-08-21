#!/usr/bin/env python3 

from scapy.all import *

"""
get_if_hwaddr(interface): returns the interfaces MAC
get_if_addr(interface): returns the interface's ip address
sendp(packet, iface=""): sends packet across iface, iface is required
ret_tcp_packet = srp1(packet, iface="") : returns first response packet after using sendp

Ether Layer Arguments:
    - src  : Source MAC address 
    - dst  : Destination MAC address 

IP Layer Arguments:
    - src   : Source IP address 
    - dst   : Destination IP address 

The packet should have `IP proto=0x42`.\nThe packet should be sent to the other host on the network.
"""