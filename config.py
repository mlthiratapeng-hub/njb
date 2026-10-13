# config.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PREFIX = "!"

OWNER_ID = 1488103702488154173
LOG_CHANNEL_ID = 1557064238940299376

# ── TrueMoney ──
TRUEMONEY_PHONE  = "0837751528"
TRUEMONEY_API_KEY = os.getenv("TM_API_KEY", "")

# Cloudflare Worker relay — แทนการยิง TrueMoney ตรง
TM_RELAY_URL    = os.getenv(
    "TM_RELAY_URL",
    "https://tm-relay.umai46488.workers.dev",
)
TM_RELAY_SECRET = os.getenv("TM_RELAY_SECRET", "njb_9x7f2k1p")

# ── MHDDoS ──
MHDDOS_PATH     = os.getenv("MHDDOS_PATH", "start.py")
MHDDOS_FULL     = os.path.join(BASE_DIR, MHDDOS_PATH)
MHDDOS_DIR      = os.path.dirname(MHDDOS_FULL)
MHDDOS_LAUNCHER = os.path.join(BASE_DIR, "mhddos_launcher.py")

# ── Multi-vector DDoS ──
THREADS_PER_SUB_NODE = 200
RPC_PER_SUB_NODE     = 128
STACK_SIZE_BYTES     = 256 * 1024

# ── Respawn ──
MAX_RESPAWN_ATTEMPTS = 5
RESPAWN_DELAY        = 2

ATTACK_LOG_DIR = os.path.join(BASE_DIR, "data", "attack_logs")

# ── Proxy ──
PROXY_SOURCES = [
    "https://proxy5.net/th/free-proxy/thailand/socks5",
    "https://proxy5.net/th/free-proxy/thailand/http",
]
PROXY_FETCH_TIMEOUT        = 45
PROXY_VALIDATE_TIMEOUT     = 5
PROXY_VALIDATE_CONCURRENCY = 150
PROXY_UPDATE_INTERVAL      = 600
PROXY_CACHE_FILE           = os.path.join(BASE_DIR, "data", "proxies_cache.txt")
PROXIES_PER_SUB_NODE       = 20


def proxy_slice_file(user_id: int, index: int) -> str:
    return os.path.join(BASE_DIR, "data", f"px_{user_id}_{index}.txt")


# ── Limits ──
MAX_DURATION         = 300
MIN_DEVICES          = 1
MAX_DEVICES_PURCHASE = 5

FORBIDDEN_TLDS = [".th", ".gov"]
FORBIDDEN_IPS  = ["127.0.0.1", "localhost", "0.0.0.0"]
MAX_WARNINGS   = 3

# ── Emojis (animated <a:...) ต้องมี quote ครอบ ──
EMOJI_DDOS_HEADER   = "<a:1000035910:1559173862820810803>"
EMOJI_CONTACT       = "<:1000035915:1559174417097953340>"
EMOJI_SHOP_HEADER   = "<:1000035915:1559174417097953340>"
EMOJI_RULES         = "<a:1000038732:1559175829001338980>"
EMOJI_ALLOWED       = "<a:1000035725:1559279254125019217>"
EMOJI_BULLET        = "<a:1000035904:1559278995374088252>"
EMOJI_MODULE        = "<:1000035866:1559279147648290947>"
EMOJI_CHOOSE_MODULE = "<:1000038746:1559184363021795369>"
EMOJI_PICK          = "<a:1000030144:1559280351254151199>"