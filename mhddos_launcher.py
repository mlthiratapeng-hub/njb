# mhddos_launcher.py
"""
Wrapper ที่บีบ stack size ของทุก thread ลงเหลือ 512KB
ก่อนจะ exec start.py ของ MHDDoS
→ ทำให้ threads มากขึ้นได้โดยไม่กิน RAM
"""
import os
import sys
import threading
import resource

# บีบ stack ของ main process (inherited by child threads)
try:
    resource.setrlimit(resource.RLIMIT_STACK, (512 * 1024, 512 * 1024))
except (ValueError, OSError):
    pass

# บีบ stack ของ Python threads ที่จะสร้าง
try:
    threading.stack_size(512 * 1024)
except (ValueError, RuntimeError):
    pass

# หา start.py
here = os.path.dirname(os.path.abspath(__file__))
start_py = os.path.join(here, "start.py")
os.chdir(here)

# ส่ง args ต่อให้ start.py
sys.argv = [start_py] + sys.argv[1:]

# รัน start.py เป็น __main__
import runpy
runpy.run_path(start_py, run_name="__main__")