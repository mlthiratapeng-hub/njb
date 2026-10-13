# proxy_manager.py
import asyncio
import re
import aiohttp
from bs4 import BeautifulSoup
from config import (
    PROXY_SOURCES, PROXY_UPDATE_INTERVAL,
    PROXY_FETCH_TIMEOUT, PROXY_VALIDATE_TIMEOUT,
    PROXY_VALIDATE_CONCURRENCY,
    PROXY_CACHE_FILE, PROXIES_PER_SUB_NODE,
)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class ProxyManager:
    def __init__(self):
        self.proxies: list[str] = []
        self._lock = asyncio.Lock()
        self.ready = asyncio.Event()

    # ── fetch จากทุก source ──
    async def fetch(self) -> list[str]:
        found: list[str] = []
        for url in PROXY_SOURCES:
            try:
                async with aiohttp.ClientSession(headers={"User-Agent": _UA}) as s:
                    async with s.get(url, timeout=PROXY_FETCH_TIMEOUT) as r:
                        html = await r.text()
            except Exception:
                continue

            soup = BeautifulSoup(html, "html.parser")
            for row in soup.find_all("tr"):
                cols = [td.get_text(strip=True) for td in row.find_all("td")]
                if len(cols) >= 2 and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", cols[0]):
                    try:
                        if 1 <= int(cols[1]) <= 65535:
                            found.append(f"{cols[0]}:{cols[1]}")
                    except ValueError:
                        pass

        # dedupe
        found = list(dict.fromkeys(found))

        if found:
            self.proxies = found
            self._save_cache(found)
        else:
            self.proxies = self._load_cache()
        return self.proxies

    # ── validate 1 proxy ──
    async def validate(self, proxy: str) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "http://httpbin.org/ip",
                    proxy=f"http://{proxy}",
                    timeout=PROXY_VALIDATE_TIMEOUT,
                ) as r:
                    return r.status == 200
        except Exception:
            return False

    # ── validate pool ทั้งหมด ──
    async def refresh_and_validate(self):
        raw = await self.fetch()
        if not raw:
            return []

        sem = asyncio.Semaphore(PROXY_VALIDATE_CONCURRENCY)
        good: list[str] = []

        async def check(p):
            async with sem:
                if await self.validate(p):
                    good.append(p)

        await asyncio.gather(*(check(p) for p in raw))
        async with self._lock:
            self.proxies = good
            self._save_cache(good)
        return good

    # ── slice pool สำหรับ sub-nodes ──
    def slice_for_subnodes(self, sub_node_count: int) -> list[list[str]]:
        """
        แบ่ง pool เป็น sub_node_count slice
        round-robin — diversity สูงสุดต่อ sub-node
        """
        pool = self.proxies or self._load_cache()
        if not pool:
            return [[] for _ in range(sub_node_count)]

        # เป้า: PROXIES_PER_SUB_NODE ต่อ node — ถ้า pool เล็กกว่า ใช้เท่าที่มี
        target = min(len(pool), PROXIES_PER_SUB_NODE * sub_node_count)
        pool = pool[:target]

        chunks: list[list[str]] = [[] for _ in range(sub_node_count)]
        for i, p in enumerate(pool):
            chunks[i % sub_node_count].append(p)
        return chunks

    # ── cache ──
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

    # ── loop ──
    async def auto_refresh_loop(self):
        # รอบแรก — บล็อกจนกว่าจะโหลดเสร็จ หรือ timeout 90 วิ
        try:
            await asyncio.wait_for(self.refresh_and_validate(), timeout=90)
        except (asyncio.TimeoutError, Exception):
            pass
        self.ready.set()
        print(f"[VANTA] proxy pool ready: {len(self.proxies)} proxies")

        while True:
            try:
                await asyncio.sleep(PROXY_UPDATE_INTERVAL)
                await self.refresh_and_validate()
                print(f"[VANTA] proxy refreshed: {len(self.proxies)} proxies")
            except asyncio.CancelledError:
                raise
            except Exception:
                pass