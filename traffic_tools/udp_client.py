# -*- coding: utf-8 -*-
"""
-------------------------------------------------
   File Name     UDP_server
   Description : For traffic testing
   Author :      yuqian.shi@outlook.com
   date:         2023/7/14
-------------------------------------------------
"""
import socket
from scapy.all import *
import sys
def get_dst_mac(src_inf):
    local_ip = get_if_addr(src_inf)
    peer_ip = local_ip
    # TODO get peer ip properly
    if peer_ip.endswith("2"):
        peer_ip = peer_ip[:-1]+'1'
    else:
        peer_ip = peer_ip[:-1]+'2'
    return getmacbyip(peer_ip)
if len(sys.argv)!=5:
    print(f'please input src_addr,dst_addr,interface,packet_num( e.g. python3 {sys.argv[0]} 192.168.1.1:54321 192.168.1.2:12345 eth_1_2 5)')
    sys.exit(-1)
src_addr = sys.argv[1]
dst_addr = sys.argv[2]
src_inf = sys.argv[3]
packet_num = int(sys.argv[4])
src_ip,src_port = src_addr.split(":")
dst_ip,dst_port = dst_addr.split(":")
src_port = int(src_port)
dst_port = int(dst_port)
dst_mac = get_dst_mac(src_inf)
for i in range(packet_num):
    p  = Ether(dst=dst_mac) /IP(src=src_ip, dst=dst_ip) / UDP(sport=src_port, dport=dst_port) / Raw(str(i).encode("utf-8"))
    sendp(p,iface=src_inf,verbose=True)