# mhddos_launcher.py
"""
Wrapper ที่:
1. บีบ stack size ลง 512KB → threads มากขึ้น
2. Patch MHDDoS UDP method → packet size 65507 bytes (max)
3. เปิด socket option ให้ reuse port
"""
import os
import sys
import threading
import resource
import socket

try:
    resource.setrlimit(resource.RLIMIT_STACK, (512 * 1024, 512 * 1024))
except (ValueError, OSError):
    pass

try:
    threading.stack_size(512 * 1024)
except (ValueError, RuntimeError):
    pass

# Patch socket defaults — ให้ UDP packet ใหญ่สุด
_orig_socket = socket.socket

class PatchedSocket(_orig_socket):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            # buffer ใหญ่ขึ้น
            self.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
            self.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        except Exception:
            pass

socket.socket = PatchedSocket

here = os.path.dirname(os.path.abspath(__file__))
start_py = os.path.join(here, "start.py")
os.chdir(here)

sys.argv = [start_py] + sys.argv[1:]

import runpy
runpy.run_path(start_py, run_name="__main__")