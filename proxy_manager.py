# proxy_manager.py
import asyncio
import re
import aiohttp
from bs4 import BeautifulSoup
from config import (
    PROXY_SOURCE_URL, PROXY_UPDATE_INTERVAL,
    PROXY_CACHE_FILE, PROXIES_PER_DEVICE, proxy_attack_file,
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class ProxyManager:
    def __init__(self):
        self.proxies: list[str] = []
        self._lock = asyncio.Lock()

    async def fetch(self) -> list[str]:
        try:
            async with aiohttp.ClientSession(headers={"User-Agent": _UA}) as s:
                async with s.get(PROXY_SOURCE_URL, timeout=20) as r:
                    html = await r.text()
        except Exception:
            return self._load_cache()

        soup = BeautifulSoup(html, "html.parser")
        found: list[str] = []
        for row in soup.find_all("tr"):
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) >= 2 and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", cols[0]):
                try:
                    if 1 <= int(cols[1]) <= 65535:
                        found.append(f"{cols[0]}:{cols[1]}")
                except ValueError:
                    pass

        if found:
            self.proxies = found
            self._save_cache(found)
        else:
            self.proxies = self._load_cache()
        return self.proxies

    async def validate(self, proxy: str, timeout: int = 5) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "http://httpbin.org/ip",
                    proxy=f"http://{proxy}",
                    timeout=timeout,
                ) as r:
                    return r.status == 200
        except Exception:
            return False

    async def refresh_and_validate(self):
        raw = await self.fetch()
        if not raw:
            return []
        sem = asyncio.Semaphore(50)
        good: list[str] = []

        async def check(p):
            async with sem:
                if await self.validate(p):
                    good.append(p)

        await asyncio.gather(*(check(p) for p in raw[:500]))
        async with self._lock:
            self.proxies = good
            self._save_cache(good)
        return good

    def write_for_devices(self, user_id: int, devices: int) -> int:
        """
        เขียน proxy ลงไฟล์แยกตาม user_id
        คืนจำนวน proxy ที่เขียน (0 = ไม่มี → caller ต้องแจ้ง user)
        """
        need = max(PROXIES_PER_DEVICE, devices * PROXIES_PER_DEVICE)
        pool = self.proxies or self._load_cache()
        if not pool:
            return 0
        selected = pool[:need]
        try:
            with open(proxy_attack_file(user_id), "w") as f:
                f.write("\n".join(selected))
        except OSError:
            return 0
        return len(selected)

    def _save_cache(self, proxies: list[str]):
        try:
            with open(PROXY_CACHE_FILE, "w") as f:
                f.write("\n".join(proxies))
        except OSError:
            pass

    def _load_cache(self) -> list[str]:
        try:
            with open(PROXY_CACHE_FILE) as f:
                return [l.strip() for l in f if l.strip()]
        except OSError:
            return []

    async def auto_refresh_loop(self):
        while True:
            try:
                await self.refresh_and_validate()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(PROXY_UPDATE_INTERVAL)