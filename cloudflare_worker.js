// cloudflare_worker.js
// Deploy ผ่าน Cloudflare Dashboard → Workers → Create

export default {
  async fetch(request, env) {
    // ตรวจ secret ป้องกันคนอื่นยิง worker เรา
    const url = new URL(request.url);
    const secret = url.searchParams.get("key");
    if (secret !== env.WORKER_SECRET) {
      return new Response("forbidden", { status: 403 });
    }

    // รับ voucher hash + phone จาก body
    let body;
    try {
      body = await request.json();
    } catch {
      return new Response(JSON.stringify({ error: "bad_json" }), {
        status: 400,
        headers: { "content-type": "application/json" },
      });
    }

    const { voucher, phone } = body;
    if (!voucher || !phone) {
      return new Response(JSON.stringify({ error: "missing_params" }), {
        status: 400,
        headers: { "content-type": "application/json" },
      });
    }

    const tmUrl = `https://gift.truemoney.com/campaign/vouchers/${voucher}/redeem`;
    const payload = { mobile: phone, voucher_hash: voucher };

    const headers = {
      "Content-Type": "application/json",
      "Accept": "application/json, text/plain, */*",
      "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
      "Origin": "https://gift.truemoney.com",
      "Referer": `https://gift.truemoney.com/campaign/?v=${voucher}`,
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    };

    try {
      const r = await fetch(tmUrl, {
        method: "POST",
        headers,
        body: JSON.stringify(payload),
      });
      const text = await r.text();
      return new Response(text, {
        status: r.status,
        headers: {
          "content-type": "application/json",
          "access-control-allow-origin": "*",
        },
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: "fetch_failed", message: String(e) }), {
        status: 502,
        headers: { "content-type": "application/json" },
      });
    }
  },
};