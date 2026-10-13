# truemoney.py
import re
import json
import aiohttp
from config import TRUEMONEY_PHONE, TM_RELAY_URL, TM_RELAY_SECRET


class TrueMoneyClient:
    def __init__(self, phone: str = TRUEMONEY_PHONE):
        self.phone = phone

    async def redeem(self, gift_link: str) -> dict:
        voucher = self._extract_voucher(gift_link)
        if not voucher:
            return {"success": False, "amount": 0,
                    "raw": {"error": "invalid_link"}}

        phones = self._phone_variants()
        last_raw = None

        for phone in phones:
            result = await self._redeem_via_relay(voucher, phone)
            if result["success"]:
                return result
            last_raw = result["raw"]

            code = self._status_code(result["raw"])
            if code and code not in (
                "PHONE_NUMBER_INVALID", "INVALID_PHONE_NUMBER", "INVALID_PARAM"
            ):
                break

        return {"success": False, "amount": 0, "raw": last_raw or {}}

    async def _redeem_via_relay(self, voucher: str, phone: str) -> dict:
        url = f"{TM_RELAY_URL}?key={TM_RELAY_SECRET}"
        payload = {"voucher": voucher, "phone": phone}

        print(f"[TM/relay] POST phone={phone} voucher={voucher[:8]}...",
              flush=True)

        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json=payload,
                                  timeout=aiohttp.ClientTimeout(total=25)) as r:
                    text = await r.text()
                    print(f"[TM/relay] status={r.status} body={text[:300]}",
                          flush=True)
        except Exception as e:
            return {"success": False, "amount": 0,
                    "raw": {"error": f"relay_exc: {e}"}}

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return {"success": False, "amount": 0,
                    "raw": {"error": "response_not_json",
                            "status": r.status, "body": text[:300]}}

        status = data.get("status", {}).get("code", "")
        print(f"[TM] status_code={status}", flush=True)

        if status == "SUCCESS":
            try:
                amount = float(data["data"]["my_ticket"]["amount_baht"])
            except (KeyError, TypeError, ValueError):
                return {"success": False, "amount": 0, "raw": data}
            return {"success": True, "amount": amount, "raw": data}

        return {"success": False, "amount": 0, "raw": data}

    def _phone_variants(self) -> list[str]:
        p = self.phone.strip().replace(" ", "").replace("-", "")
        variants = [p]
        if p.startswith("0"):
            variants.append("+66" + p[1:])
        elif p.startswith("+66"):
            variants.append("0" + p[3:])
        return list(dict.fromkeys(variants))

    @staticmethod
    def _status_code(raw) -> str:
        if not isinstance(raw, dict):
            return ""
        status = raw.get("status")
        if not isinstance(status, dict):
            return ""
        return status.get("code", "") or ""

    def _extract_voucher(self, link: str) -> str | None:
        m = re.search(r"[?&]v=([A-Za-z0-9]+)", link)
        if m:
            return m.group(1)
        m = re.search(r"/vouchers/([A-Za-z0-9]+)", link)
        if m:
            return m.group(1)
        return None