# truemoney.py
import re
import json
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
                "raw": {"error": "invalid link — ไม่เจอ v= ในลิงก์"}
            }

        # ลอง 2 format: 08XXXXXXXX และ +668XXXXXXXX
        phone_candidates = self._phone_variants()

        last_raw = None
        for phone in phone_candidates:
            result = await self._try_redeem(voucher, phone)
            if result["success"]:
                return result
            last_raw = result["raw"]

            # ถ้า error ไม่ใช่เรื่อง format เบอร์ → ไม่ต้องลองซ้ำ
            code = self._status_code(result["raw"])
            if code not in ("PHONE_NUMBER_INVALID", "INVALID_PHONE_NUMBER", "INVALID_PARAM", ""):
                break

        return {"success": False, "amount": 0, "raw": last_raw or {}}

    def _phone_variants(self) -> list[str]:
        """คืนรูปแบบเบอร์ที่อาจใช้ได้"""
        p = self.phone.strip().replace(" ", "").replace("-", "")
        variants = [p]
        if p.startswith("0"):
            variants.append("+66" + p[1:])
            variants.append("66" + p[1:])
        elif p.startswith("+66"):
            variants.append("0" + p[3:])
        return list(dict.fromkeys(variants))  # dedupe

    async def _try_redeem(self, voucher: str, phone: str) -> dict:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
            "Origin": "https://gift.truemoney.com",
            "Referer": f"https://gift.truemoney.com/campaign/?v={voucher}",
        }
        payload = {"mobile": phone, "voucher_hash": voucher}
        url = f"{self.base}/{voucher}/redeem"

        print(f"[TM] POST {url} phone={phone}", flush=True)

        try:
            async with aiohttp.ClientSession(headers=headers) as s:
                async with s.post(url, json=payload, timeout=20) as r:
                    text = await r.text()
                    print(f"[TM] status={r.status} body={text[:500]}", flush=True)
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError:
                        return {
                            "success": False, "amount": 0,
                            "raw": {
                                "error": "response_not_json",
                                "status": r.status,
                                "body": text[:500],
                            }
                        }
        except aiohttp.ClientError as e:
            return {
                "success": False, "amount": 0,
                "raw": {"error": f"network: {e}"}
            }
        except Exception as e:
            return {
                "success": False, "amount": 0,
                "raw": {"error": f"unknown: {e}"}
            }

        status = data.get("status", {}).get("code", "")
        print(f"[TM] status_code={status}", flush=True)

        if status == "SUCCESS":
            try:
                amount = float(data["data"]["my_ticket"]["amount_baht"])
            except (KeyError, TypeError, ValueError):
                return {"success": False, "amount": 0, "raw": data}
            return {"success": True, "amount": amount, "raw": data}

        return {"success": False, "amount": 0, "raw": data}

    @staticmethod
    def _status_code(raw: dict) -> str:
        if not isinstance(raw, dict):
            return ""
        return raw.get("status", {}).get("code", "")

    def _extract_voucher(self, link: str) -> str | None:
        # รองรับทั้ง ?v=XXX และ /vouchers/XXX/redeem
        m = re.search(r"[?&]v=([A-Za-z0-9]+)", link)
        if m:
            return m.group(1)
        m = re.search(r"/vouchers/([A-Za-z0-9]+)", link)
        if m:
            return m.group(1)
        return None