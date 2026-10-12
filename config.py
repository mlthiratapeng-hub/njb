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

# MHDDoS
MHDDOS_PATH = os.getenv("MHDDOS_PATH", "start.py")
MHDDOS_FULL = os.path.join(BASE_DIR, MHDDOS_PATH)

# Proxy
PROXY_SOURCE_URL = "https://proxy5.net/th/free-proxy/thailand"
PROXY_UPDATE_INTERVAL = 1800
PROXY_CACHE_FILE  = os.path.join(BASE_DIR, "data", "proxies_cache.txt")
PROXIES_PER_DEVICE = 5

# C6: per-user proxy file — แต่ละ user ได้ไฟล์แยก ไม่ทับกัน
def proxy_attack_file(user_id: int) -> str:
    return os.path.join(BASE_DIR, "data", f"proxies_attack_{user_id}.txt")

# Attack limits
MAX_DURATION = 300
MIN_DEVICES = 1
MAX_DEVICES_PURCHASE = 5

# Forbidden
FORBIDDEN_TLDS = [".th", ".gov"]
FORBIDDEN_IPS  = ["127.0.0.1", "localhost", "0.0.0.0"]

# Warning
MAX_WARNINGS = 3

# Emojis — animated emoji (<a:) ต้องคงค่าไว้ ห้ามลบ
EMOJI_DDOS_HEADER   = "<a:1000035910:1559173862820810803>"
EMOJI_CONTACT       = "<:1000035915:1559174417097953340>"
EMOJI_SHOP_HEADER   = "<:1000035915:1559174417097953340>"
EMOJI_RULES         = "<a:1000038732:1559175829001338980>"
EMOJI_ALLOWED       = "<a:1000035725:1559279254125019217>"
EMOJI_BULLET        = "<a:1000035904:1559278995374088252>"
EMOJI_MODULE        = "<:1000035866:1559279147648290947>"
EMOJI_CHOOSE_MODULE = "<:1000038746:1559184363021795369>"
EMOJI_PICK          = "<a:1000030144:1559280351254151199>"