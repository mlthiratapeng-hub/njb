# database.py
import os, time, secrets, string, aiosqlite
from config import DATA_DIR, DB_PATH, OWNER_ID


class Database:
    def __init__(self, path=DB_PATH):
        self.path = path

    async def init(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    virus_expires_at INTEGER DEFAULT 0,
                    virus_forever INTEGER DEFAULT 0
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    key TEXT PRIMARY KEY,
                    owner_id INTEGER,
                    expires_at INTEGER,
                    forever INTEGER DEFAULT 0,
                    note TEXT DEFAULT ''
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS attacks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER, target TEXT, port INTEGER,
                    mode TEXT, duration INTEGER, started_at INTEGER
                )
            """)
            await db.commit()

    # ── users / virus ──
    async def get_user(self, uid):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE user_id=?", (uid,)) as cur:
                r = await cur.fetchone()
                return dict(r) if r else None

    async def add_virus(self, uid, secs, forever=False):
        await self.get_user(uid)
        exp = 0 if forever else int(time.time()) + secs
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users SET virus_expires_at=?, virus_forever=? WHERE user_id=?",
                             (exp, 1 if forever else 0, uid))
            await db.commit()

    async def remove_virus(self, uid):
        await self.get_user(uid)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users SET virus_expires_at=0, virus_forever=0 WHERE user_id=?", (uid,))
            await db.commit()

    async def has_virus(self, uid):
        u = await self.get_user(uid)
        if not u: return False
        if u["virus_forever"]: return True
        return int(time.time()) < (u["virus_expires_at"] or 0)

    # ── api keys ──
    async def create_key(self, owner_id, secs, forever=False, note=""):
        key = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(32))
        exp = 0 if forever else int(time.time()) + secs
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO api_keys (key, owner_id, expires_at, forever, note) VALUES (?,?,?,?,?)",
                             (key, owner_id, exp, 1 if forever else 0, note))
            await db.commit()
        return key

    async def check_key(self, key):
        if not key: return False
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM api_keys WHERE key=?", (key,)) as cur:
                r = await cur.fetchone()
                if not r: return False
                r = dict(r)
                if r["forever"]: return True
                return int(time.time()) < (r["expires_at"] or 0)

    async def ensure_owner_key(self):
        """สร้าง key ถาวรของ owner ถ้ายังไม่มี"""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT key FROM api_keys WHERE owner_id=? AND forever=1 LIMIT 1",
                                  (OWNER_ID,)) as cur:
                r = await cur.fetchone()
                if r: return r["key"]
        return await self.create_key(OWNER_ID, 0, forever=True, note="owner")

    async def log_attack(self, uid, target, port, mode, dur):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO attacks (user_id, target, port, mode, duration, started_at) VALUES (?,?,?,?,?,?)",
                             (uid, target, port, mode, dur, int(time.time())))
            await db.commit()