# ui_components.py
import os
import discord
from config import (
    BASE_DIR,
    EMOJI_DDOS_HEADER, EMOJI_CONTACT, EMOJI_RULES, EMOJI_ALLOWED,
    EMOJI_BULLET, EMOJI_MODULE, EMOJI_CHOOSE_MODULE, EMOJI_PICK,
    EMOJI_SHOP_HEADER,
)

ASSET_ATTACK_BANNER  = os.path.join(BASE_DIR, "assets", "attack_banner.jpg")
ASSET_ATTACK_RUNNING = os.path.join(BASE_DIR, "assets", "attack_running.jpg")
ASSET_SHOP_BANNER    = os.path.join(BASE_DIR, "assets", "shop_banner.jpg")


# ============================================================
# Modal: Attack
# ============================================================
class AttackModal(discord.ui.Modal, title="DDOS ATTACK"):
    target = discord.ui.TextInput(
        label="Target IP / URL",
        placeholder="example.com หรือ 1.2.3.4",
        required=True, max_length=200,
    )
    port = discord.ui.TextInput(
        label="Port", placeholder="80 / 443 / 25565",
        required=True, max_length=5,
    )
    duration = discord.ui.TextInput(
        label="Time Limit (วินาที, สูงสุด 300)",
        placeholder="300", required=True, max_length=3,
    )
    device = discord.ui.TextInput(
        label="Device (จำนวนเครื่องที่ใช้)",
        placeholder="1", required=True, max_length=2,
    )

    async def on_submit(self, interaction: discord.Interaction):
        from bot import handle_attack_submit
        await handle_attack_submit(interaction, self)


# ============================================================
# Modal: Topup
# ============================================================
class TopupModal(discord.ui.Modal, title="เติมเงิน"):
    link = discord.ui.TextInput(
        label="ลิงก์ซองทรูมันนี่",
        placeholder="https://gift.truemoney.com/campaign/?v=...",
        required=True, max_length=300,
    )

    async def on_submit(self, interaction: discord.Interaction):
        from bot import process_topup
        await process_topup(interaction, self.link.value)


# ============================================================
# ปุ่มขอ Device
# ============================================================
class DeviceRequestButton(discord.ui.Button):
    def __init__(self, allowed_user_id: int):
        super().__init__(
            label="ขอ Device",
            style=discord.ButtonStyle.secondary,
            custom_id="device_request",
            emoji=EMOJI_PICK,
        )
        self.allowed_user_id = allowed_user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.allowed_user_id:
            await interaction.response.send_message(
                "ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงถุ้ย", ephemeral=True
            )
            return
        await interaction.response.send_modal(AttackModal())


# ============================================================
# Module select + view
# ============================================================
class ModuleSelect(discord.ui.Select):
    def __init__(self, user_id: int, target: str, port: int,
                 duration: int, devices: int):
        options = [
            discord.SelectOption(label="มายคราฟ",     value="minecraft", emoji="⛏️"),
            discord.SelectOption(label="โรบอค",        value="roblox",    emoji="🎮"),
            discord.SelectOption(label="ห้องเสียงดิส", value="discord",   emoji="🔊"),
            discord.SelectOption(label="ยิงเว็บ",      value="web",       emoji="🌐"),
            discord.SelectOption(label="ฟีฟาย",       value="fivem",     emoji="🚔"),
        ]
        super().__init__(placeholder="เลือกโมดูล", options=options,
                         custom_id="module_select")
        self.user_id = user_id
        self.target = target
        self.port = port
        self.duration = duration
        self.devices = devices

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "ไม่ใช่คำสั่งของมึง", ephemeral=True
            )
            return

        try:
            await interaction.message.edit(view=None)
        except discord.HTTPException:
            pass

        from bot import start_attack
        await start_attack(interaction, self.values[0], self.target,
                           self.port, self.duration, self.devices)


class ModuleView(discord.ui.View):
    def __init__(self, user_id: int, target: str, port: int,
                 duration: int, devices: int):
        super().__init__(timeout=600)
        self.add_item(ModuleSelect(user_id, target, port, duration, devices))


# ============================================================
# Attack panel (persistent)
# ============================================================
class AttackPanel(discord.ui.View):
    def __init__(self, allowed_user_id: int):
        super().__init__(timeout=None)
        self.add_item(DeviceRequestButton(allowed_user_id))


# ============================================================
# Embeds
# ============================================================
def build_attack_embed(with_image: bool = True) -> discord.Embed:
    em = discord.Embed(
        title=f"{EMOJI_DDOS_HEADER} DDOS ATTACK",
        color=discord.Color.pink(),
        description=(
            f"{EMOJI_CONTACT} สนใจติดต่อได้เลยย\n\n"
            f"{EMOJI_RULES} **กฎการใช้**\n"
            f"ห้ามยิงเว็บ `.th` `.gov` Local IP (`127.0.0.1`)\n\n"
            f"{EMOJI_ALLOWED} **Ddos ได้**\n"
            f"เว็บอะไรต่างๆนอกเหนือจากเว็บที่ห้าม {EMOJI_BULLET}\n\n"
            f"ฟีฟาย {EMOJI_BULLET}\n"
            f"โรบอค {EMOJI_BULLET}\n"
            f"มายคราฟ {EMOJI_BULLET}\n"
            f"ห้องเสียงดิส {EMOJI_BULLET}\n\n"
            f"หากจะยิงอะไรต่างๆโปรดเลือก Module ให้ถูก {EMOJI_MODULE}"
        ),
    )
    if with_image:
        em.set_image(url="attachment://attack_banner.jpg")
    return em


def build_module_embed() -> discord.Embed:
    return discord.Embed(
        title=f"{EMOJI_CHOOSE_MODULE} เลือกโมดูล",
        color=discord.Color.blurple(),
        description=(
            f"{EMOJI_ALLOWED} เลือกโมดูลให้ถูกด้วยนะจะได้ยิงให้ดับได้\n\n"
            "1. มายคราฟ\n"
            "2. โรบอค\n"
            "3. ห้องเสียงดิส\n"
            "4. ยิงเว็บ\n"
            "5. ฟีฟาย"
        ),
    )


def build_attack_running_embed(target: str, time_left: int,
                               speed: str, module: str,
                               nodes: str = "-",
                               proxies: str = "0",
                               with_image: bool = True) -> discord.Embed:
    em = discord.Embed(
        title=f"{EMOJI_PICK} DDOS ATTACK",
        color=discord.Color.pink(),
        description=(
            f"**IP:URL TERGET:** `{target}`\n"
            f"**TIME:** `{time_left}s`\n"
            f"**SPEED WEB:** `{speed}`\n"
            f"**NODES:** `{nodes}`\n"
            f"**PROXIES:** `{proxies}`\n"
            f"**MODULE:** `{module}`"
        ),
    )
    if with_image:
        em.set_image(url="attachment://attack_running.jpg")
    return em


# ============================================================
# Shop
# ============================================================
class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="เช่า-ซื้อDevice",
                       style=discord.ButtonStyle.primary,
                       custom_id="shop_buy_device")
    async def buy_device(self, interaction: discord.Interaction,
                         button: discord.ui.Button):
        await interaction.response.send_message(
            "เลือกประเภท:", view=DeviceTypeView(), ephemeral=True
        )

    @discord.ui.button(label="เช็คเงิน",
                       style=discord.ButtonStyle.secondary,
                       custom_id="shop_check_balance")
    async def check_balance(self, interaction: discord.Interaction,
                            button: discord.ui.Button):
        from bot import db
        user = await db.get_user(interaction.user.id)
        if not user:
            await interaction.response.send_message("DB error", ephemeral=True)
            return
        await interaction.response.send_message(
            f"💰 มี **{user['balance']:.0f}💵**\n"
            f"เคยเติมรวม **{user['total_deposited']:.0f}💵**\n"
            f"Device: **{user['devices']}** เครื่อง",
            ephemeral=True,
        )

    @discord.ui.button(label="เติมตัง",
                       style=discord.ButtonStyle.success,
                       custom_id="shop_topup")
    async def topup(self, interaction: discord.Interaction,
                    button: discord.ui.Button):
        await interaction.response.send_modal(TopupModal())


def build_shop_embed(with_image: bool = True) -> discord.Embed:
    em = discord.Embed(
        title=f"{EMOJI_SHOP_HEADER} ซื้อยศ",
        color=discord.Color.dark_grey(),
        description="**เช่าDevice-ซื้อDevice** กดด้านล่างเลยยย",
    )
    if with_image:
        em.set_image(url="attachment://shop_banner.jpg")
    return em


# ---------- Device type ----------
class DeviceTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="เช่า Device", value="rent"),
            discord.SelectOption(label="ซื้อ Device", value="buy"),
        ]
        super().__init__(placeholder="เลือกประเภท", options=options,
                         custom_id="device_type")

    async def callback(self, interaction: discord.Interaction):
        from bot import shop_device_type_selected
        await shop_device_type_selected(interaction, self.values[0])


class DeviceTypeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(DeviceTypeSelect())


# ---------- Prices ----------
RENT_PRICES = {
    "1h": {1: 10, 2: 15, 3: 20, 4: 25, 5: 30},
    "1d": {1: 15, 2: 20, 3: 25, 4: 30, 5: 35},
    "3d": {1: 25, 2: 35, 3: 45, 4: 55, 5: 65},
    "7d": {1: 40, 2: 60, 3: 80, 4: 100, 5: 120},
}
BUY_PRICES = {1: 100, 2: 190, 3: 280, 4: 370, 5: 460}

RENT_SECONDS = {
    "1h": 3600,
    "1d": 86400,
    "3d": 3 * 86400,
    "7d": 7 * 86400,
}


class QuantitySelect(discord.ui.Select):
    def __init__(self, mode: str, period: str | None = None):
        self.mode = mode
        self.period = period
        if mode == "rent":
            labels = [(f"{i} Device", i) for i in range(1, 6)]
        else:
            labels = [(f"ซื้อ {i} Device", i) for i in range(1, 6)]
        options = [discord.SelectOption(label=l, value=str(v))
                   for l, v in labels]
        super().__init__(placeholder="เลือกจำนวน", options=options,
                         custom_id=f"qty_{mode}")

    async def callback(self, interaction: discord.Interaction):
        from bot import shop_quantity_selected
        await shop_quantity_selected(
            interaction, self.mode, self.period, int(self.values[0])
        )


class QuantityView(discord.ui.View):
    def __init__(self, mode: str, period: str | None = None):
        super().__init__(timeout=120)
        self.add_item(QuantitySelect(mode, period))


class PeriodSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="ยศทดลอง 1 ชม", value="1h"),
            discord.SelectOption(label="เช่า 1วัน",     value="1d"),
            discord.SelectOption(label="เช่า 3วัน",     value="3d"),
            discord.SelectOption(label="เช่า 7วัน",     value="7d"),
        ]
        super().__init__(placeholder="เลือกระยะเวลา", options=options,
                         custom_id="period")

    async def callback(self, interaction: discord.Interaction):
        from bot import shop_period_selected
        await shop_period_selected(interaction, self.values[0])


class PeriodView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(PeriodSelect())