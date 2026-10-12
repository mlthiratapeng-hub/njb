# truemoney.py
import re
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
            return {"success": False, "amount": 0,
                    "raw": {"error": "invalid link"}}

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }
        payload = {"mobile": self.phone, "voucher_hash": voucher}

        try:
            async with aiohttp.ClientSession(headers=headers) as s:
                async with s.post(
                    f"{self.base}/{voucher}/redeem",
                    json=payload, timeout=20,
                ) as r:
                    data = await r.json()
        except Exception as e:
            return {"success": False, "amount": 0, "raw": {"error": str(e)}}

        status = data.get("status", {}).get("code", "")
        if status == "SUCCESS":
            amount = float(data["data"]["my_ticket"]["amount_baht"])
            return {"success": True, "amount": amount, "raw": data}
        return {"success": False, "amount": 0, "raw": data}

    def _extract_voucher(self, link: str) -> str | None:
        m = re.search(r"v=([a-zA-Z0-9]+)", link)
        return m.group(1) if m else None