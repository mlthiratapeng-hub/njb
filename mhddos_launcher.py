# mhddos_launcher.py
import os
import sys
import threading
import resource

try:
    resource.setrlimit(resource.RLIMIT_STACK, (256 * 1024, 256 * 1024))
except (ValueError, OSError):
    pass

try:
    threading.stack_size(256 * 1024)
except (ValueError, RuntimeError):
    pass

here = os.path.dirname(os.path.abspath(__file__))
start_py = os.path.join(here, "start.py")
os.chdir(here)

sys.argv = [start_py] + sys.argv[1:]

import runpy
runpy.run_path(start_py, run_name="__main__")