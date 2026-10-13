# truemoney.py
import re
import json
import asyncio
import aiohttp
from config import TRUEMONEY_PHONE, TRUEMONEY_API_KEY


class TrueMoneyClient:
    def __init__(self, phone: str = TRUEMONEY_PHONE,
                 api_key: str = TRUEMONEY_API_KEY):
        self.phone = phone
        self.api_key = api_key
        self.base = "https://gift.truemoney.com/campaign/vouchers"

    async def redeem(self, gift_link: str) -> dict:
        voucher = self._extract_voucher(gift_link)
        if not voucher:
            return {
                "success": False, "amount": 0,
                "raw": {"error": "invalid_link"}
            }

        phones = self._phone_variants()
        last_raw = None

        for phone in phones:
            # ลอง curl_cffi ก่อน (TLS impersonate Chrome)
            result = await self._try_curl_cffi(voucher, phone)
            if result["success"]:
                return result
            last_raw = result["raw"]

            # ถ้า CF block → ลอง cloudscraper
            if self._is_cf_block(result["raw"]):
                print("[TM] CF block detected — ลอง cloudscraper", flush=True)
                result = await self._try_cloudscraper(voucher, phone)
                if result["success"]:
                    return result
                last_raw = result["raw"]

            code = self._status_code(result["raw"])
            if code and code not in (
                "PHONE_NUMBER_INVALID", "INVALID_PHONE_NUMBER", "INVALID_PARAM"
            ):
                break

        return {"success": False, "amount": 0, "raw": last_raw or {}}

    # ─────────────────────────────────────────────────────
    # Method A: curl_cffi (TLS fingerprint ของ Chrome จริง)
    # ─────────────────────────────────────────────────────
    async def _try_curl_cffi(self, voucher: str, phone: str) -> dict:
        try:
            from curl_cffi.requests import AsyncSession
        except ImportError:
            print("[TM] curl_cffi ยังไม่ได้ติดตั้ง — ข้ามไป", flush=True)
            return {
                "success": False, "amount": 0,
                "raw": {"error": "curl_cffi_not_installed"}
            }

        url = f"{self.base}/{voucher}/redeem"
        payload = {"mobile": phone, "voucher_hash": voucher}
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
            "Origin": "https://gift.truemoney.com",
            "Referer": f"https://gift.truemoney.com/campaign/?v={voucher}",
        }
        print(f"[TM/curl_cffi] POST {url} phone={phone}", flush=True)

        try:
            async with AsyncSession() as s:
                r = await s.post(
                    url, json=payload, headers=headers,
                    impersonate="chrome120", timeout=20,
                )
                text = r.text
                print(f"[TM/curl_cffi] status={r.status_code} "
                      f"body={text[:300]}", flush=True)
        except Exception as e:
            return {
                "success": False, "amount": 0,
                "raw": {"error": f"curl_cffi_exc: {e}"}
            }

        return self._parse_response(r.status_code, text)

    # ─────────────────────────────────────────────────────
    # Method B: cloudscraper (แก้ JS challenge)
    # ─────────────────────────────────────────────────────
    async def _try_cloudscraper(self, voucher: str, phone: str) -> dict:
        try:
            import cloudscraper
        except ImportError:
            print("[TM] cloudscraper ยังไม่ได้ติดตั้ง — ข้ามไป", flush=True)
            return {
                "success": False, "amount": 0,
                "raw": {"error": "cloudscraper_not_installed"}
            }

        url = f"{self.base}/{voucher}/redeem"
        payload = {"mobile": phone, "voucher_hash": voucher}
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
            "Origin": "https://gift.truemoney.com",
            "Referer": f"https://gift.truemoney.com/campaign/?v={voucher}",
        }
        print(f"[TM/cloudscraper] POST {url} phone={phone}", flush=True)

        def _do():
            scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows",
                         "mobile": False}
            )
            return scraper.post(url, json=payload, headers=headers, timeout=20)

        try:
            r = await asyncio.to_thread(_do)
            text = r.text
            print(f"[TM/cloudscraper] status={r.status_code} "
                  f"body={text[:300]}", flush=True)
        except Exception as e:
            return {
                "success": False, "amount": 0,
                "raw": {"error": f"cloudscraper_exc: {e}"}
            }

        return self._parse_response(r.status_code, text)

    # ─────────────────────────────────────────────────────
    # Parser
    # ─────────────────────────────────────────────────────
    def _parse_response(self, status: int, text: str) -> dict:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # CF challenge หรือ HTML อื่น
            return {
                "success": False, "amount": 0,
                "raw": {
                    "error": "response_not_json",
                    "status": status,
                    "body": text[:500],
                }
            }

        code = data.get("status", {}).get("code", "")
        print(f"[TM] status_code={code}", flush=True)

        if code == "SUCCESS":
            try:
                amount = float(data["data"]["my_ticket"]["amount_baht"])
            except (KeyError, TypeError, ValueError):
                return {"success": False, "amount": 0, "raw": data}
            return {"success": True, "amount": amount, "raw": data}

        return {"success": False, "amount": 0, "raw": data}

    # ─────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────
    def _phone_variants(self) -> list[str]:
        p = self.phone.strip().replace(" ", "").replace("-", "")
        variants = [p]
        if p.startswith("0"):
            variants.append("+66" + p[1:])
            variants.append("66" + p[1:])
        elif p.startswith("+66"):
            variants.append("0" + p[3:])
        return list(dict.fromkeys(variants))

    @staticmethod
    def _status_code(raw) -> str:
        # กัน crash: raw อาจเป็น int / str / None
        if not isinstance(raw, dict):
            return ""
        status = raw.get("status")
        if not isinstance(status, dict):
            return ""
        return status.get("code", "") or ""

    @staticmethod
    def _is_cf_block(raw) -> bool:
        if not isinstance(raw, dict):
            return False
        if raw.get("error") != "response_not_json":
            return False
        body = raw.get("body", "")
        return "cloudflare" in body.lower() or "attention required" in body.lower()

    def _extract_voucher(self, link: str) -> str | None:
        m = re.search(r"[?&]v=([A-Za-z0-9]+)", link)
        if m:
            return m.group(1)
        m = re.search(r"/vouchers/([A-Za-z0-9]+)", link)
        if m:
            return m.group(1)
        return None