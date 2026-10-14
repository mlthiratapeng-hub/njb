# database.py
import os, time, aiosqlite
from config import DATA_DIR, DB_PATH


class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path

    async def init(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    virus_expires_at INTEGER DEFAULT 0,
                    virus_forever INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP)
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS attacks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER, target TEXT, port INTEGER,
                    mode TEXT, duration INTEGER, started_at INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP)
            """)
            await db.commit()

    async def get_user(self, user_id):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                             (user_id,))
            await db.commit()
            async with db.execute("SELECT * FROM users WHERE user_id = ?",
                                  (user_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def add_virus(self, user_id, secs, forever=False):
        await self.get_user(user_id)
        exp = 0 if forever else int(time.time()) + secs
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users SET virus_expires_at=?, virus_forever=? "
                             "WHERE user_id=?", (exp, 1 if forever else 0, user_id))
            await db.commit()

    async def remove_virus(self, user_id):
        await self.get_user(user_id)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("UPDATE users SET virus_expires_at=0, virus_forever=0 "
                             "WHERE user_id=?", (user_id,))
            await db.commit()

    async def has_virus(self, user_id) -> bool:
        u = await self.get_user(user_id)
        if not u: return False
        if u["virus_forever"]: return True
        return int(time.time()) < (u["virus_expires_at"] or 0)

    async def log_attack(self, user_id, target, port, mode, duration):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO attacks "
                             "(user_id, target, port, mode, duration, started_at) "
                             "VALUES (?, ?, ?, ?, ?, ?)",
                             (user_id, target, port, mode, duration, int(time.time())))
            await db.commit()