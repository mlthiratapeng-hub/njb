# config.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PREFIX = "!"

OWNER_ID = 1488103702488154173
LOG_CHANNEL_ID = 1557064238940299376

# TrueMoney
TRUEMONEY_PHONE = "0837751528"
TRUEMONEY_API_KEY = os.getenv("TM_API_KEY", "")

# MHDDoS — absolute path
MHDDOS_PATH = os.getenv("MHDDOS_PATH", "start.py")
MHDDOS_FULL = os.path.join(BASE_DIR, MHDDOS_PATH)
MHDDOS_DIR  = os.path.dirname(MHDDOS_FULL)

# ── Attack power ──
SUB_NODES_PER_DEVICE = 5      # 1 device → 5 sub-process
THREADS_PER_SUB_NODE = 500    # ต่อ sub-process
RPC_PER_SUB_NODE     = 128    # requests per connection

# ── Proxy ──
PROXY_SOURCES = [
    "https://proxy5.net/th/free-proxy/thailand/socks5",
    "https://proxy5.net/th/free-proxy/thailand/http",
]
PROXY_FETCH_TIMEOUT  = 45     # ยาวขึ้น — รอ source ตอบ
PROXY_VALIDATE_TIMEOUT = 5
PROXY_VALIDATE_CONCURRENCY = 150
PROXY_UPDATE_INTERVAL = 600   # refresh ทุก 10 นาที
PROXY_CACHE_FILE = os.path.join(BASE_DIR, "data", "proxies_cache.txt")
PROXIES_PER_SUB_NODE = 20     # เป้า — proxy ต่อ 1 sub-node


def proxy_slice_file(user_id: int, index: int) -> str:
    """ไฟล์ proxy แยกต่อ (user, sub-node)"""
    return os.path.join(BASE_DIR, "data", f"px_{user_id}_{index}.txt")


# ── Limits ──
MAX_DURATION = 300
MIN_DEVICES = 1
MAX_DEVICES_PURCHASE = 5

# ── Forbidden ──
FORBIDDEN_TLDS = [".th", ".gov"]
FORBIDDEN_IPS  = ["127.0.0.1", "localhost", "0.0.0.0"]

MAX_WARNINGS = 3

# ── Emojis ──
EMOJI_DDOS_HEADER   = "<a:1000035910:1559173862820810803>"
EMOJI_CONTACT       = "<:1000035915:1559174417097953340>"
EMOJI_SHOP_HEADER   = "<:1000035915:1559174417097953340>"
EMOJI_RULES         = "<a:1000038732:1559175829001338980>"
EMOJI_ALLOWED       = "<a:1000035725:1559279254125019217>"
EMOJI_BULLET        = "<a:1000035904:1559278995374088252>"
EMOJI_MODULE        = "<:1000035866:1559279147648290947>"
EMOJI_CHOOSE_MODULE = "<:1000038746:1559184363021795369>"
EMOJI_PICK          = "<a:1000030144:1559280351254151199>"