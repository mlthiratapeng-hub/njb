# database.py
import aiosqlite
import time

DB_PATH = "data/bot.db"


class Database:
    def __init__(self, path=DB_PATH):
        self.path = path

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    balance REAL DEFAULT 0,
                    devices INTEGER DEFAULT 0,
                    warnings INTEGER DEFAULT 0,
                    banned INTEGER DEFAULT 0,
                    total_deposited REAL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS device_rentals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    devices INTEGER,
                    expires_at INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    type TEXT,
                    detail TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS attacks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    target TEXT,
                    port INTEGER,
                    duration INTEGER,
                    module TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.commit()

    # ---------- users ----------
    async def get_user(self, user_id: int):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,)
            )
            await db.commit()
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def update_user(self, user_id: int, **kwargs):
        if not kwargs:
            return
        await self.get_user(user_id)
        fields = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [user_id]
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                f"UPDATE users SET {fields} WHERE user_id = ?", values
            )
            await db.commit()

    async def add_devices(self, user_id: int, amount: int) -> int:
        user = await self.get_user(user_id)
        new_dev = max(0, user["devices"] + amount)
        await self.update_user(user_id, devices=new_dev)
        return new_dev

    async def add_balance(self, user_id: int, amount: float,
                          type_: str, detail: str = "") -> float:
        user = await self.get_user(user_id)
        new_bal = user["balance"] + amount
        await self.update_user(user_id, balance=new_bal)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO transactions (user_id, amount, type, detail) "
                "VALUES (?, ?, ?, ?)",
                (user_id, amount, type_, detail),
            )
            await db.commit()
        return new_bal

    async def add_warning(self, user_id: int) -> int:
        user = await self.get_user(user_id)
        new_warn = user["warnings"] + 1
        await self.update_user(user_id, warnings=new_warn)
        if new_warn >= 3:
            await self.update_user(user_id, banned=1)
        return new_warn

    async def set_ban(self, user_id: int, banned: bool):
        await self.update_user(user_id, banned=1 if banned else 0)

    # ---------- rentals ----------
    async def add_rental(self, user_id: int, devices: int, expires_at_ts: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO device_rentals (user_id, devices, expires_at) "
                "VALUES (?, ?, ?)",
                (user_id, devices, expires_at_ts),
            )
            await db.commit()

    async def pop_expired_rentals(self):
        now = int(time.time())
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM device_rentals WHERE expires_at <= ?", (now,)
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
            for r in rows:
                await db.execute(
                    "UPDATE users SET devices = MAX(0, devices - ?) "
                    "WHERE user_id = ?",
                    (r["devices"], r["user_id"]),
                )
                await db.execute(
                    "DELETE FROM device_rentals WHERE id = ?", (r["id"],)
                )
            await db.commit()
        return rows

    # ---------- attacks ----------
    async def log_attack(self, user_id: int, target: str, port: int,
                         duration: int, module: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO attacks (user_id, target, port, duration, module) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, target, port, duration, module),
            )
            await db.commit()