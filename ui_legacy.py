# ui_legacy.py
import discord
from config import (
    EMOJI_CONTACT, EMOJI_ALLOWED, EMOJI_BUTTON,
    L7_EMOJI, L4_EMOJI, CUSTOM_EMOJI, L7_METHODS, L4_METHODS,
)


def build_panel():
    em = discord.Embed(
        title="Ddos Attack",
        color=discord.Color.pink(),
        description=(
            f"{EMOJI_CONTACT} วันละ 35 นะครับ ถาวร 500\n\n"
            "มี **API ขายด้วย** วันละ 20 เชื่อมบอทได้ ยิงได้หมดไม่มีข้อห้าม\n"
            "เกม เว็บ อะไรต่างๆ\n\n"
            f"{EMOJI_ALLOWED} **กฎการใช้**\n"
            "ห้ามยิง Local IP `.th` `.gov`\n"
            "แต่ซื้อ API ไปทำบอทได้ ยิงได้หมด"
        ),
    )
    view = discord.ui.View(timeout=None)
    view.add_item(PanelButton())
    return {"embed": em, "view": view}


class PanelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="",
            style=discord.ButtonStyle.secondary,
            custom_id="panel_req",
            emoji=EMOJI_BUTTON,
        )

    async def callback(self, interaction):
        from bot import open_attack_modal
        await open_attack_modal(interaction)


class AttackModal(discord.ui.Modal, title="Ddos Attack"):
    target = discord.ui.TextInput(
        label="IP:URL TERGET", placeholder="example.com",
        required=True, max_length=200,
    )
    port = discord.ui.TextInput(
        label="PORT (1-65535)", placeholder="443",
        required=True, max_length=5,
    )
    duration = discord.ui.TextInput(
        label="TIME (MAX 250)", placeholder="120",
        required=True, max_length=3,
    )

    async def on_submit(self, interaction):
        from bot import handle_attack_submit
        await handle_attack_submit(interaction, self)


def build_category_view(uid, target, port, dur):
    em = discord.Embed(
        title="เลือกโหมด",
        color=discord.Color.blurple(),
        description=f"```\nIP:URL : {target}\nPORT   : {port}\nTIME   : {dur}s\n```",
    )
    view = discord.ui.View(timeout=300)
    view.add_item(CatButton("L7 (เว็บ)", "l7", uid, target, port, dur, discord.ButtonStyle.primary))
    view.add_item(CatButton("L4 (เกม)", "l4", uid, target, port, dur, discord.ButtonStyle.danger))
    view.add_item(CatButton("MODE-HTTPS", "custom", uid, target, port, dur, discord.ButtonStyle.success))
    return {"embed": em, "view": view}


class CatButton(discord.ui.Button):
    def __init__(self, label, key, uid, target, port, dur, style):
        super().__init__(label=label, style=style, custom_id=f"cat_{key}")
        self.key, self.uid = key, uid
        self.target, self.port, self.dur = target, port, dur

    async def callback(self, interaction):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("ไม่ใช่คำสั่งของมึง", ephemeral=True)
            return
        from bot import show_method_panel
        await show_method_panel(interaction, self.key, self.target, self.port, self.dur)


def build_method_view(cat, uid, target, port, dur):
    if cat == "l7":
        title, methods, style = "L7 Methods", L7_METHODS, discord.ButtonStyle.primary
    elif cat == "l4":
        title, methods, style = "L4 Methods", L4_METHODS, discord.ButtonStyle.danger
    else:
        title = "Custom Methods"
        methods = ["HTTPS", "HTTPSLOAD", "DDOS-BROWSER", "BYPASS-CF",
                   "BYPASS-CDN", "DDOS-H2", "TLS", "HTTP-RPS",
                   "VC-DISCORD", "FREEFIRE"]
        style = discord.ButtonStyle.success

    em = discord.Embed(
        title=title, color=discord.Color.blurple(),
        description=f"```\nIP:URL : {target}\nPORT   : {port}\nTIME   : {dur}s\n```",
    )
    view = discord.ui.View(timeout=300)
    for m in methods:
        view.add_item(MethodButton(m, uid, target, port, dur, style))
    return {"embed": em, "view": view}


class MethodButton(discord.ui.Button):
    def __init__(self, method, uid, target, port, dur, style):
        super().__init__(label=method, style=style, custom_id=f"m_{method}")
        self.method, self.uid = method, uid
        self.target, self.port, self.dur = target, port, dur

    async def callback(self, interaction):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("ไม่ใช่คำสั่งของมึง", ephemeral=True)
            return
        from bot import fire_attack
        await fire_attack(interaction, self.method, self.target, self.port, self.dur)


def build_running(method, target, port, left, total, speed, hits=0):
    em = discord.Embed(
        title="DDOS ATTACK",
        color=discord.Color.dark_grey(),
        description=(
            f"**IP:URL :** `{target}`\n"
            f"**PORT :** `{port}`\n"
            f"**MODE :** `{method}`\n"
            f"**SPEED :** `{speed}`\n"
            f"**TIME :** `{left}s` / `{total}s`"
        ),
    )
    return {"embed": em}


def build_finished(method, target, port, total, hits=0):
    em = discord.Embed(
        title="✅ ยิงเสร็จแล้ว",
        color=discord.Color.green(),
        description=(
            f"**IP:URL :** `{target}`\n"
            f"**PORT :** `{port}`\n"
            f"**MODE :** `{method}`\n"
            f"**TIME :** `{total}s`\n"
            f"**HITS :** `{hits}`"
        ),
    )
    return {"embed": em}