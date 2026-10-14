# ui_v2.py
import discord
from discord import ui
from config import (
    EMOJI_HEADER, EMOJI_CONTACT, EMOJI_ALLOWED, EMOJI_BUTTON,
    L7_EMOJI, L4_EMOJI, CUSTOM_EMOJI, L7_METHODS, L4_METHODS,
)

V2_FLAGS = discord.MessageFlags.components_v2


def _wrap(view):
    return {"view": view, "flags": V2_FLAGS}


def build_panel():
    v = ui.LayoutView(timeout=None)
    c = ui.Container()
    c.add_item(ui.TextDisplay(f"# {EMOJI_HEADER} Ddos Attack"))
    c.add_item(ui.TextDisplay(
        f"{EMOJI_CONTACT} วันละ 35 นะครับ ถาวร 500\n\n"
        "มี **API ขายด้วย** วันละ 20 เชื่อมบอทได้ ยิงได้หมดไม่มีข้อห้าม\n"
        "เกม เว็บ อะไรต่างๆ"
    ))
    # ✅ แก้บั๊กเส้นคั่น: ใช้ divider=False เพื่อไม่ให้มีเส้น
    c.add_item(ui.Separator(divider=False, spacing=ui.SeparatorSpacing.small))
    c.add_item(ui.TextDisplay(
        f"{EMOJI_ALLOWED} **กฎการใช้**\n"
        "ห้ามยิง Local IP `.th` `.gov`\n"
        "แต่ซื้อ API ไปทำบอทได้ ยิงได้หมด"
    ))
    # ✅ ปุ่มอยู่ใน Container เดียวกัน (ไม่แยกออกไป)
    c.add_item(ui.ActionRow().add_item(PanelButton()))
    v.add_item(c)
    return _wrap(v)


class PanelButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="",
            style=discord.ButtonStyle.secondary,
            custom_id="panel_req",
            emoji=EMOJI_BUTTON,
        )

    async def callback(self, interaction: discord.Interaction):
        from bot import open_attack_modal
        await open_attack_modal(interaction)


class AttackModal(ui.Modal, title="Ddos Attack"):
    target = ui.TextInput(label="IP:URL TERGET", placeholder="example.com", required=True, max_length=200)
    port = ui.TextInput(label="PORT (1-65535)", placeholder="443", required=True, max_length=5)
    duration = ui.TextInput(label="TIME (MAX 250)", placeholder="120", required=True, max_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        from bot import handle_attack_submit
        await handle_attack_submit(interaction, self)


class CatButton(ui.Button):
    def __init__(self, label, key, uid, target, port, dur, style):
        super().__init__(label=label, style=style, custom_id=f"cat_{key}")
        self.key, self.uid = key, uid
        self.target, self.port, self.dur = target, port, dur

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("ไม่ใช่คำสั่งของมึง", ephemeral=True)
            return
        from bot import show_method_panel
        await show_method_panel(interaction, self.key, self.target, self.port, self.dur)


def build_category_view(uid, target, port, dur):
    v = ui.LayoutView(timeout=300)
    c = ui.Container()
    c.add_item(ui.TextDisplay("# เลือกโหมด"))
    c.add_item(ui.TextDisplay(f"```\n[+] IP:URL : {target}\n[+] PORT : {port}\n[+] TIME : {dur}s\n```"))
    row = ui.ActionRow()
    row.add_item(CatButton("L7 (เว็บ)", "l7", uid, target, port, dur, discord.ButtonStyle.primary))
    row.add_item(CatButton("L4 (เกม)", "l4", uid, target, port, dur, discord.ButtonStyle.danger))
    row.add_item(CatButton("MODE-HTTPS", "custom", uid, target, port, dur, discord.ButtonStyle.success))
    c.add_item(row)
    v.add_item(c)
    return _wrap(v)


class MethodButton(ui.Button):
    def __init__(self, method, emoji, uid, target, port, dur, style):
        super().__init__(label=method, style=style, custom_id=f"m_{method}", emoji=emoji)
        self.method, self.uid = method, uid
        self.target, self.port, self.dur = target, port, dur

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.uid:
            await interaction.response.send_message("ไม่ใช่คำสั่งของมึง", ephemeral=True)
            return
        from bot import fire_attack
        await fire_attack(interaction, self.method, self.target, self.port, self.dur)


def _rows(methods, emap, uid, target, port, dur, style, per=5):
    rows = []
    for i in range(0, len(methods), per):
        row = ui.ActionRow()
        for m in methods[i:i + per]:
            row.add_item(MethodButton(m, emap.get(m), uid, target, port, dur, style))
        rows.append(row)
    return rows


def build_method_view(cat, uid, target, port, dur):
    v = ui.LayoutView(timeout=300)
    c = ui.Container()
    if cat == "l7":
        title, methods, emap, style = "# L7 Methods", L7_METHODS, L7_EMOJI, discord.ButtonStyle.primary
    elif cat == "l4":
        title, methods, emap, style = "# L4 Methods", L4_METHODS, L4_EMOJI, discord.ButtonStyle.danger
    else:
        title = "# Custom Methods"
        methods = ["HTTPS", "HTTPSLOAD", "DDOS-BROWSER", "BYPASS-CF", "BYPASS-CDN", "DDOS-H2", "TLS", "HTTP-RPS", "VC-DISCORD", "FREEFIRE"]
        emap, style = CUSTOM_EMOJI, discord.ButtonStyle.success
    c.add_item(ui.TextDisplay(title))
    c.add_item(ui.TextDisplay(f"```\n[+] IP:URL : {target}\n[+] PORT : {port}\n[+] TIME : {dur}s\n```"))
    for r in _rows(methods, emap, uid, target, port, dur, style):
        c.add_item(r)
    v.add_item(c)
    return _wrap(v)


def build_running(method, target, port, left, total, speed, hits=0):
    v = ui.LayoutView(timeout=None)
    c = ui.Container()
    c.add_item(ui.TextDisplay("# DDOS ATTACK"))
    c.add_item(ui.TextDisplay(
        f"**IP:URL :** `{target}`\n"
        f"**PORT :** `{port}`\n"
        f"**MODE :** `{method}`\n"
        f"**SPEED :** `{speed}`\n"
        f"**TIME :** `{left}s` / `{total}s`"
    ))
    v.add_item(c)
    return _wrap(v)


def build_finished(method, target, port, total, hits=0):
    v = ui.LayoutView(timeout=None)
    c = ui.Container()
    c.add_item(ui.TextDisplay("ยิงเสร็จแล้ว"))
    c.add_item(ui.TextDisplay(
        f"**IP:URL :** `{target}`\n"
        f"**PORT :** `{port}`\n"
        f"**MODE :** `{method}`\n"
        f"**TIME :** `{total}s`\n"
        f"**HITS :** `{hits}`"
    ))
    v.add_item(c)
    return _wrap(v)