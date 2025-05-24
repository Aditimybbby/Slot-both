import aiosqlite
from datetime import datetime

DB_FILE = "slotbot.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS slots(
    slot_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id      INTEGER NOT NULL,
    channel_id    INTEGER UNIQUE NOT NULL,
    user_id       INTEGER NOT NULL,
    slot_name     TEXT,
    created_at    TEXT,
    duration_days INTEGER
);
CREATE TABLE IF NOT EXISTS pings(
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id  INTEGER,
    date_key    TEXT,
    ping_count  INTEGER
);
"""

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def add_slot(guild_id, channel_id, user_id, name, days):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO slots(guild_id,channel_id,user_id,slot_name,created_at,duration_days) "
            "VALUES(?,?,?,?,?,?)",
            (guild_id, channel_id, user_id, name, datetime.utcnow().isoformat(), days)
        )
        await db.commit()

async def get_slot_by_channel(channel_id):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT * FROM slots WHERE channel_id = ?", (channel_id,))
        return await cur.fetchone()

async def remove_slot(channel_id):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM slots WHERE channel_id = ?", (channel_id,))
        await db.execute("DELETE FROM pings WHERE channel_id = ?", (channel_id,))
        await db.commit()

async def bump_ping(channel_id, date_key):
    async with aiosqlite.connect(DB_FILE) as db:
        cur = await db.execute("SELECT ping_count FROM pings WHERE channel_id = ? AND date_key = ?",
                               (channel_id, date_key))
        row = await cur.fetchone()
        if row:
            new_count = row[0] + 1
            await db.execute("UPDATE pings SET ping_count = ? WHERE channel_id = ? AND date_key = ?",
                             (new_count, channel_id, date_key))
        else:
            new_count = 1
            await db.execute("INSERT INTO pings(channel_id,date_key,ping_count) VALUES(?,?,?)",
                             (channel_id, date_key, new_count))
        await db.commit()
        return new_count

async def update_slot_owner(channel_id, new_user_id):
    """Transfer a slot to a new owner."""
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE slots SET user_id = ? WHERE channel_id = ?",
            (new_user_id, channel_id))
        await db.commit()
