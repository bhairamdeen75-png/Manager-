"""Turso (libSQL) data layer for the bot — async + cached.

All functions keep the exact same names as the earlier sync/MongoDB version,
but are now `async def` and must be awaited — this is what lets the bot
handle many groups concurrently without one slow DB call freezing everyone
else (the actual network I/O runs in a worker thread via asyncio.to_thread,
so the event loop never blocks on it).

Hot-path reads (settings, filters, auto-responses, smart-replies — checked
on almost every single message) are cached in-memory for a few seconds and
invalidated on write, so an active group doesn't re-query Turso for every
message.
"""

import asyncio
import json
import logging
import time

import turso_serverless

from config import TURSO_DATABASE_URL, TURSO_AUTH_TOKEN

logger = logging.getLogger(__name__)

if not TURSO_DATABASE_URL:
    raise SystemExit(
        "❌ TURSO_DATABASE_URL env var set nahi hai. Turso dashboard se database "
        "URL aur auth token lekar env vars me daalo."
    )

_conn = turso_serverless.connect(TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)


def _reconnect():
    """Turso (libSQL over HTTP) streams get closed server-side after being
    idle for a while (or the Render free instance sleeps/wakes). The driver
    keeps re-using the same stream id from the original connect() call, so
    once that stream is gone every query fails with something like:
        OperationalError: HTTP status 404: stream not found: d1b1c3f4:...
    There was no recovery for this before — the process just kept throwing
    on every DB call until it was manually restarted. Re-connect and swap
    the module-level handle in place.
    """
    global _conn
    logger.warning("Turso stream mar gaya tha, reconnect kar rahe hain...")
    _conn = turso_serverless.connect(TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)


def _is_stream_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "stream not found" in msg or "404" in msg


# ---------------- Low-level SQL helpers ----------------
# Actual network call blocking hai (turso_serverless sync driver hai), isliye
# thread pool me chalate hain taaki bot ka asyncio event loop free rahe.

def _sync_query(sql, params):
    try:
        cur = _conn.execute(sql, params)
    except Exception as e:
        if not _is_stream_error(e):
            raise
        _reconnect()
        cur = _conn.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _sync_exec(sql, params):
    try:
        cur = _conn.execute(sql, params)
        _conn.commit()
    except Exception as e:
        if not _is_stream_error(e):
            raise
        _reconnect()
        cur = _conn.execute(sql, params)
        _conn.commit()
    return getattr(cur, "lastrowid", None)


async def _query(sql: str, params=()):
    """SELECT helper — dict rows ki list return karta hai."""
    return await asyncio.to_thread(_sync_query, sql, params)


async def _exec(sql: str, params=()):
    """INSERT/UPDATE/DELETE helper — commit karke lastrowid (agar ho) return karta hai."""
    return await asyncio.to_thread(_sync_exec, sql, params)


def _exec_sync_startup(sql: str, params=()):
    """Sirf startup (init_db) ke liye — event loop chalu hone se pehle, sync theek hai."""
    cur = _conn.execute(sql, params)
    _conn.commit()
    return cur


# ---------------- Tiny in-memory TTL cache (hot-path reads ke liye) ----------------

_CACHE_TTL = 20  # seconds — itni der me settings/filter change shayad hi ho
_cache: dict = {}


def _cache_get(key):
    entry = _cache.get(key)
    if entry and entry[0] > time.time():
        return entry[1]
    return None


def _cache_set(key, value):
    _cache[key] = (time.time() + _CACHE_TTL, value)


def _cache_drop(key):
    _cache.pop(key, None)


# ---------------- Settings: generic EAV helpers (jitni bhi settings hain sab isi table me) ----------------

async def _settings_snapshot(chat_id: int) -> dict:
    """Is chat ki saari settings ek dict me — cached, Mongo ke find_one() jaisa."""
    key = ("settings", chat_id)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    rows = await _query("SELECT key, value FROM settings WHERE chat_id=?", (chat_id,))
    snap = {r["key"]: (json.loads(r["value"]) if r["value"] is not None else None) for r in rows}
    _cache_set(key, snap)
    return snap


async def _get_setting(chat_id: int, field: str, default=None):
    snap = await _settings_snapshot(chat_id)
    val = snap.get(field, None)
    return default if val is None else val


async def _set_setting(chat_id: int, field: str, value):
    await _exec(
        "INSERT INTO settings (chat_id, key, value) VALUES (?, ?, ?) "
        "ON CONFLICT(chat_id, key) DO UPDATE SET value = excluded.value",
        (chat_id, field, json.dumps(value)),
    )
    _cache_drop(("settings", chat_id))


class _SettingsCollectionCompat:
    """handlers/settings_panel.py, handlers/security.py, handlers/smartreply.py
    seedhe db.settings_col.find_one()/update_one() use karte hain (Mongo style) —
    ye chhota compat wrapper unhe bina chhede chalne deta hai. Ab await karna
    padega: `await db.settings_col.find_one(...)`."""

    async def find_one(self, query):
        chat_id = query["chat_id"]
        snap = await _settings_snapshot(chat_id)
        if not snap:
            return None
        doc = dict(snap)
        doc["chat_id"] = chat_id
        return doc

    async def update_one(self, query, update, upsert=True):
        chat_id = query["chat_id"]
        for k, v in update.get("$set", {}).items():
            await _set_setting(chat_id, k, v)


settings_col = _SettingsCollectionCompat()


def init_db():
    """Saari tables (agar exist nahi karti) bana deta hai. Startup pe (event loop
    shuru hone se pehle) sync call hoti hai — safe hai, har baar chalti hai."""
    try:
        _exec_sync_startup("SELECT 1")
    except Exception as e:
        raise SystemExit(
            f"❌ Turso se connect nahi ho paya. TURSO_DATABASE_URL / TURSO_AUTH_TOKEN "
            f"env vars check karo. Error: {e}"
        )

    _exec_sync_startup("""CREATE TABLE IF NOT EXISTS warns (
        chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, count INTEGER DEFAULT 0,
        PRIMARY KEY (chat_id, user_id))""")
    _exec_sync_startup("""CREATE TABLE IF NOT EXISTS filters (
        chat_id INTEGER NOT NULL, word TEXT NOT NULL, PRIMARY KEY (chat_id, word))""")
    _exec_sync_startup("""CREATE TABLE IF NOT EXISTS settings (
        chat_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT,
        PRIMARY KEY (chat_id, key))""")
    _exec_sync_startup("""CREATE TABLE IF NOT EXISTS notes (
        chat_id INTEGER NOT NULL, name TEXT NOT NULL, content TEXT,
        PRIMARY KEY (chat_id, name))""")
    _exec_sync_startup("""CREATE TABLE IF NOT EXISTS auto_responses (
        chat_id INTEGER NOT NULL, "trigger" TEXT NOT NULL, response TEXT,
        PRIMARY KEY (chat_id, "trigger"))""")
    _exec_sync_startup("""CREATE TABLE IF NOT EXISTS xp (
        chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        xp INTEGER DEFAULT 0, last_xp_time REAL DEFAULT 0,
        PRIMARY KEY (chat_id, user_id))""")
    _exec_sync_startup("""CREATE TABLE IF NOT EXISTS seen_users (
        chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        username TEXT, first_name TEXT, PRIMARY KEY (chat_id, user_id))""")
    _exec_sync_startup("""CREATE TABLE IF NOT EXISTS stats (
        chat_id INTEGER PRIMARY KEY, total_messages INTEGER DEFAULT 0,
        commands_used INTEGER DEFAULT 0)""")
    _exec_sync_startup("""CREATE TABLE IF NOT EXISTS groups (
        chat_id INTEGER PRIMARY KEY, title TEXT)""")
    _exec_sync_startup("""CREATE TABLE IF NOT EXISTS guess_games (
        chat_id INTEGER PRIMARY KEY, number INTEGER, tries INTEGER DEFAULT 0)""")
    _exec_sync_startup("""CREATE TABLE IF NOT EXISTS smart_replies (
        id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,
        keywords TEXT NOT NULL, response TEXT)""")
    _exec_sync_startup("""CREATE TABLE IF NOT EXISTS music_queue (
        chat_id INTEGER PRIMARY KEY, tracks TEXT, current TEXT, current_msg_id INTEGER)""")

    logger.info("Turso connected aur tables ready (%s)", TURSO_DATABASE_URL)


# ---------------- Warns ----------------

async def add_warn(chat_id: int, user_id: int) -> int:
    await _exec(
        "INSERT INTO warns (chat_id, user_id, count) VALUES (?, ?, 1) "
        "ON CONFLICT(chat_id, user_id) DO UPDATE SET count = count + 1",
        (chat_id, user_id),
    )
    rows = await _query("SELECT count FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    return rows[0]["count"] if rows else 1


async def get_warns(chat_id: int, user_id: int) -> int:
    rows = await _query("SELECT count FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    return rows[0]["count"] if rows else 0


async def reset_warns(chat_id: int, user_id: int):
    await _exec("DELETE FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))


# ---------------- Filters (cached — har message pe check hota hai) ----------------

async def add_filter(chat_id: int, word: str):
    await _exec(
        "INSERT INTO filters (chat_id, word) VALUES (?, ?) "
        "ON CONFLICT(chat_id, word) DO NOTHING",
        (chat_id, word.lower()),
    )
    _cache_drop(("filters", chat_id))


async def remove_filter(chat_id: int, word: str):
    await _exec("DELETE FROM filters WHERE chat_id=? AND word=?", (chat_id, word.lower()))
    _cache_drop(("filters", chat_id))


async def get_filters(chat_id: int):
    key = ("filters", chat_id)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    rows = await _query("SELECT word FROM filters WHERE chat_id=? ORDER BY word", (chat_id,))
    result = [r["word"] for r in rows]
    _cache_set(key, result)
    return result


# ---------------- Settings: welcome ----------------

async def set_welcome(chat_id: int, text: str):
    await _set_setting(chat_id, "welcome_text", text)


async def get_welcome(chat_id: int):
    return await _get_setting(chat_id, "welcome_text", None)


# ---------------- Link / username blocker ----------------

async def set_link_block(chat_id: int, enabled: bool):
    await _set_setting(chat_id, "link_block", bool(enabled))


async def get_link_block(chat_id: int) -> bool:
    return bool(await _get_setting(chat_id, "link_block", False))


# ---------------- Media restriction ----------------

async def set_media_restrict(chat_id: int, types_csv: str):
    await _set_setting(chat_id, "media_restrict", types_csv)


async def get_media_restrict(chat_id: int):
    val = await _get_setting(chat_id, "media_restrict", "") or ""
    return [t for t in val.split(",") if t]


# ---------------- Admin log channel ----------------

async def set_log_channel(chat_id: int, log_channel_id):
    await _set_setting(chat_id, "log_channel_id", log_channel_id)


async def get_log_channel(chat_id: int):
    return await _get_setting(chat_id, "log_channel_id", None)


# ---------------- Night mode ----------------

async def set_night_mode(chat_id: int, enabled: bool):
    await _set_setting(chat_id, "night_mode", bool(enabled))


async def get_night_mode(chat_id: int) -> bool:
    return bool(await _get_setting(chat_id, "night_mode", False))


async def set_night_time(chat_id: int, start: str, end: str):
    await _set_setting(chat_id, "night_start", start)
    await _set_setting(chat_id, "night_end", end)


async def get_night_time(chat_id: int):
    start = await _get_setting(chat_id, "night_start", "23:00")
    end = await _get_setting(chat_id, "night_end", "06:00")
    return start, end


async def get_all_night_mode_chats():
    rows = await _query("SELECT chat_id FROM settings WHERE key='night_mode' AND value='true'")
    out = []
    for r in rows:
        cid = r["chat_id"]
        out.append({
            "chat_id": cid,
            "night_start": await _get_setting(cid, "night_start", "23:00"),
            "night_end": await _get_setting(cid, "night_end", "06:00"),
        })
    return out


# ---------------- Rules / accept gate ----------------

async def set_rules(chat_id: int, text: str):
    await _set_setting(chat_id, "rules_text", text)


async def get_rules(chat_id: int):
    return await _get_setting(chat_id, "rules_text", None)


async def set_rules_gate(chat_id: int, enabled: bool):
    await _set_setting(chat_id, "rules_gate", bool(enabled))


async def get_rules_gate(chat_id: int) -> bool:
    return bool(await _get_setting(chat_id, "rules_gate", False))


# ---------------- Auto-delete join/leave ----------------

async def set_autodelete_joinleave(chat_id: int, enabled: bool):
    await _set_setting(chat_id, "autodelete_joinleave", bool(enabled))


async def get_autodelete_joinleave(chat_id: int) -> bool:
    return bool(await _get_setting(chat_id, "autodelete_joinleave", False))


# ---------------- Auto-pin ----------------

async def set_autopin(chat_id: int, enabled: bool):
    await _set_setting(chat_id, "autopin", bool(enabled))


async def get_autopin(chat_id: int) -> bool:
    return bool(await _get_setting(chat_id, "autopin", False))


# ---------------- Raid protection / slow-mode ----------------

async def set_raid_protection(chat_id: int, enabled: bool):
    await _set_setting(chat_id, "raid_protection", bool(enabled))


async def get_raid_protection(chat_id: int) -> bool:
    val = await _get_setting(chat_id, "raid_protection", None)
    if val is None:
        return True  # on by default
    return bool(val)


async def get_raid_settings(chat_id: int):
    snap = await _settings_snapshot(chat_id)
    return {
        "threshold": int(snap.get("raid_join_threshold", 5) or 5),
        "window": int(snap.get("raid_time_window", 15) or 15),
        "lock_minutes": int(snap.get("raid_lock_minutes", 10) or 10),
        "slowmode_seconds": int(snap.get("slowmode_seconds", 8) or 8),
        "slowmode_after_minutes": int(snap.get("slowmode_after_minutes", 15) or 15),
    }


async def set_raid_thresholds(chat_id: int, threshold: int = None, window: int = None, lock_minutes: int = None):
    if threshold is not None:
        await _set_setting(chat_id, "raid_join_threshold", threshold)
    if window is not None:
        await _set_setting(chat_id, "raid_time_window", window)
    if lock_minutes is not None:
        await _set_setting(chat_id, "raid_lock_minutes", lock_minutes)


# ---------------- Notes (#hashtag) ----------------

async def add_note(chat_id: int, name: str, content: str):
    await _exec(
        "INSERT INTO notes (chat_id, name, content) VALUES (?, ?, ?) "
        "ON CONFLICT(chat_id, name) DO UPDATE SET content = excluded.content",
        (chat_id, name.lower(), content),
    )


async def remove_note(chat_id: int, name: str):
    await _exec("DELETE FROM notes WHERE chat_id=? AND name=?", (chat_id, name.lower()))


async def get_note(chat_id: int, name: str):
    rows = await _query("SELECT content FROM notes WHERE chat_id=? AND name=?", (chat_id, name.lower()))
    return rows[0]["content"] if rows else None


async def list_notes(chat_id: int):
    rows = await _query("SELECT name FROM notes WHERE chat_id=? ORDER BY name", (chat_id,))
    return [r["name"] for r in rows]


# ---------------- Custom auto-responses (cached — har message pe check hota hai) ----------------

async def add_response(chat_id: int, trigger: str, response: str):
    await _exec(
        'INSERT INTO auto_responses (chat_id, "trigger", response) VALUES (?, ?, ?) '
        'ON CONFLICT(chat_id, "trigger") DO UPDATE SET response = excluded.response',
        (chat_id, trigger.lower(), response),
    )
    _cache_drop(("responses", chat_id))


async def remove_response(chat_id: int, trigger: str):
    await _exec('DELETE FROM auto_responses WHERE chat_id=? AND "trigger"=?', (chat_id, trigger.lower()))
    _cache_drop(("responses", chat_id))


async def list_responses(chat_id: int):
    key = ("responses", chat_id)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    rows = await _query(
        'SELECT "trigger", response FROM auto_responses WHERE chat_id=? ORDER BY "trigger"', (chat_id,)
    )
    result = [{"trigger": r["trigger"], "response": r["response"]} for r in rows]
    _cache_set(key, result)
    return result


# ---------------- XP + leaderboard ----------------

async def add_xp(chat_id: int, user_id: int, amount: int, cooldown_seconds: int = 30):
    """Adds XP if the user is outside their cooldown window. Returns new total, or
    None if the award was skipped because the user is still on cooldown."""
    now = time.time()
    rows = await _query("SELECT xp, last_xp_time FROM xp WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    existing = rows[0] if rows else None
    if existing and (now - (existing.get("last_xp_time") or 0)) < cooldown_seconds:
        return None

    new_xp = (existing["xp"] if existing else 0) + amount
    await _exec(
        "INSERT INTO xp (chat_id, user_id, xp, last_xp_time) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(chat_id, user_id) DO UPDATE SET xp = excluded.xp, last_xp_time = excluded.last_xp_time",
        (chat_id, user_id, new_xp, now),
    )
    return new_xp


async def get_xp(chat_id: int, user_id: int) -> int:
    rows = await _query("SELECT xp FROM xp WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    return rows[0]["xp"] if rows else 0


async def get_leaderboard(chat_id: int, limit: int = 10):
    rows = await _query(
        "SELECT user_id, xp FROM xp WHERE chat_id=? ORDER BY xp DESC LIMIT ?", (chat_id, limit)
    )
    return [{"user_id": r["user_id"], "xp": r["xp"]} for r in rows]


async def get_xp_chats():
    """Saare groups jinhone kabhi XP kamaya hai — hourly leaderboard post ke liye."""
    rows = await _query("SELECT DISTINCT chat_id FROM xp WHERE chat_id > 0")
    return [r["chat_id"] for r in rows]


# ---------------- Seen users (for /tagall) ----------------

async def track_user(chat_id: int, user_id: int, username: str, first_name: str):
    await _exec(
        "INSERT INTO seen_users (chat_id, user_id, username, first_name) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(chat_id, user_id) DO UPDATE SET username = excluded.username, "
        "first_name = excluded.first_name",
        (chat_id, user_id, username, first_name),
    )


async def get_seen_users(chat_id: int):
    rows = await _query(
        "SELECT user_id, username, first_name FROM seen_users WHERE chat_id=?", (chat_id,)
    )
    return [
        {"user_id": r["user_id"], "username": r.get("username") or "", "first_name": r.get("first_name") or ""}
        for r in rows
    ]


async def remove_seen_user(chat_id: int, user_id: int):
    await _exec("DELETE FROM seen_users WHERE chat_id=? AND user_id=?", (chat_id, user_id))


# ---------------- Stats ----------------

async def increment_message_count(chat_id: int):
    await _exec(
        "INSERT INTO stats (chat_id, total_messages, commands_used) VALUES (?, 1, 0) "
        "ON CONFLICT(chat_id) DO UPDATE SET total_messages = total_messages + 1",
        (chat_id,),
    )


async def increment_command_count(chat_id: int):
    await _exec(
        "INSERT INTO stats (chat_id, total_messages, commands_used) VALUES (?, 0, 1) "
        "ON CONFLICT(chat_id) DO UPDATE SET commands_used = commands_used + 1",
        (chat_id,),
    )


async def get_stats(chat_id: int):
    rows = await _query("SELECT total_messages, commands_used FROM stats WHERE chat_id=?", (chat_id,))
    if not rows:
        return {"total_messages": 0, "commands_used": 0}
    return {"total_messages": rows[0]["total_messages"] or 0, "commands_used": rows[0]["commands_used"] or 0}


# ---------------- Groups registry (for panel: My Groups / Owner Panel) ----------------

async def track_group(chat_id: int, title: str):
    """Called whenever the bot sees activity in a group, so we know which
    groups it's currently active in (used by the /start button panel)."""
    await _exec(
        "INSERT INTO groups (chat_id, title) VALUES (?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET title = excluded.title",
        (chat_id, title),
    )


async def remove_group(chat_id: int):
    """Called when the bot is removed/kicked from a group."""
    await _exec("DELETE FROM groups WHERE chat_id=?", (chat_id,))


async def get_all_groups():
    rows = await _query("SELECT chat_id, title FROM groups")
    return [{"chat_id": r["chat_id"], "title": r.get("title") or "Unknown Group"} for r in rows]


async def get_group_count() -> int:
    rows = await _query("SELECT COUNT(*) AS c FROM groups")
    return rows[0]["c"] if rows else 0


async def get_bot_wide_stats():
    """Aggregate counters for the owner panel."""
    total_groups = (await _query("SELECT COUNT(*) AS c FROM groups"))[0]["c"]
    total_users = (await _query("SELECT COUNT(DISTINCT user_id) AS c FROM seen_users"))[0]["c"]
    row = (await _query(
        "SELECT COALESCE(SUM(total_messages),0) AS m, COALESCE(SUM(commands_used),0) AS c FROM stats"
    ))[0]
    return {
        "groups": total_groups,
        "users": total_users,
        "messages": row["m"],
        "commands": row["c"],
    }


# ---------------- Leave message ----------------

async def set_leave_message(chat_id: int, text: str):
    await _set_setting(chat_id, "leave_msg", text)


async def get_leave_message(chat_id: int):
    return await _get_setting(chat_id, "leave_msg", None)


# ---------------- Backup / restore ----------------

_BACKUP_TABLES = {
    "notes": ("notes", ["name", "content"]),
    "filters": ("filters", ["word"]),
    "warns": ("warns", ["user_id", "count"]),
    "settings": ("settings", ["key", "value"]),
}


async def export_group_data(chat_id):
    """Saare tables se is group ka data nikaalo."""
    out = {}
    for name, (table, cols) in _BACKUP_TABLES.items():
        rows = await _query(f"SELECT {', '.join(cols)} FROM {table} WHERE chat_id=?", (chat_id,))
        if rows:
            out[name] = rows
    return out


async def import_group_data(chat_id, data):
    """JSON backup ko is group me import karo (existing overwrite)."""
    count = 0
    for name, docs in data.items():
        if name not in _BACKUP_TABLES:
            continue
        table, cols = _BACKUP_TABLES[name]
        await _exec(f"DELETE FROM {table} WHERE chat_id=?", (chat_id,))
        for doc in docs:
            values = [doc.get(c) for c in cols]
            col_list = ", ".join(f'"{c}"' if c in ("trigger", "key", "value") else c for c in cols)
            placeholders = ", ".join("?" * (len(cols) + 1))
            await _exec(
                f"INSERT INTO {table} (chat_id, {col_list}) VALUES ({placeholders})",
                [chat_id] + values,
            )
            count += 1
    _cache.clear()
    return count


# ---------------- Anti-forward ----------------

async def set_antiforward(chat_id: int, enabled: bool):
    await _set_setting(chat_id, "antiforward", bool(enabled))


async def get_antiforward(chat_id: int) -> bool:
    return bool(await _get_setting(chat_id, "antiforward", False))


# ---------------- Auto-delete join/leave with delay ----------------

async def set_autodelete_delay(chat_id: int, seconds: int):
    await _set_setting(chat_id, "autodelete_delay", seconds)


async def get_autodelete_delay(chat_id: int) -> int:
    return int(await _get_setting(chat_id, "autodelete_delay", 0) or 0)


# ---------------- Guess game (restart-proof) ----------------

async def set_guess_game(chat_id: int, number: int):
    await _exec(
        "INSERT INTO guess_games (chat_id, number, tries) VALUES (?, ?, 0) "
        "ON CONFLICT(chat_id) DO UPDATE SET number = excluded.number, tries = 0",
        (chat_id, number),
    )


async def get_guess_game(chat_id: int):
    rows = await _query("SELECT number, tries FROM guess_games WHERE chat_id=?", (chat_id,))
    if not rows:
        return None
    return {"number": rows[0]["number"], "tries": rows[0]["tries"] or 0}


async def add_guess_try(chat_id: int):
    await _exec("UPDATE guess_games SET tries = tries + 1 WHERE chat_id=?", (chat_id,))


async def delete_guess_game(chat_id: int):
    await _exec("DELETE FROM guess_games WHERE chat_id=?", (chat_id,))


# ---------------- Smart auto-replies (cached — har message pe check hota hai) ----------------

async def add_smart_reply(chat_id: int, keywords: list, response: str):
    kw_json = json.dumps(keywords)
    rows = await _query("SELECT id FROM smart_replies WHERE chat_id=? AND keywords=?", (chat_id, kw_json))
    if rows:
        await _exec("UPDATE smart_replies SET response=? WHERE id=?", (response, rows[0]["id"]))
    else:
        await _exec(
            "INSERT INTO smart_replies (chat_id, keywords, response) VALUES (?, ?, ?)",
            (chat_id, kw_json, response),
        )
    _cache_drop(("smart_replies", chat_id))


async def remove_smart_reply(chat_id: int, word: str) -> bool:
    """Word jis bhi keyword-set me mile, wo pehla smart reply delete karo (Mongo delete_one jaisa)."""
    rows = await _query("SELECT id, keywords FROM smart_replies WHERE chat_id=?", (chat_id,))
    for r in rows:
        if word in json.loads(r["keywords"]):
            await _exec("DELETE FROM smart_replies WHERE id=?", (r["id"],))
            _cache_drop(("smart_replies", chat_id))
            return True
    return False


async def list_smart_replies(chat_id: int):
    key = ("smart_replies", chat_id)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    rows = await _query("SELECT keywords, response FROM smart_replies WHERE chat_id=?", (chat_id,))
    result = [{"keywords": json.loads(r["keywords"]), "response": r["response"]} for r in rows]
    _cache_set(key, result)
    return result


# ---------------- Music queue (handlers/music.py) ----------------

async def get_music_queue(chat_id: int):
    rows = await _query(
        "SELECT tracks, current, current_msg_id FROM music_queue WHERE chat_id=?", (chat_id,)
    )
    if not rows:
        return {}
    r = rows[0]
    return {
        "tracks": json.loads(r["tracks"]) if r["tracks"] else [],
        "current": json.loads(r["current"]) if r["current"] else None,
        "current_msg_id": r["current_msg_id"],
    }


async def save_music_queue(chat_id: int, tracks, current=None, current_msg_id=None):
    await _exec(
        "INSERT INTO music_queue (chat_id, tracks, current, current_msg_id) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET tracks = excluded.tracks, current = excluded.current, "
        "current_msg_id = excluded.current_msg_id",
        (chat_id, json.dumps(tracks), json.dumps(current) if current is not None else None, current_msg_id),
    )


async def clear_music_queue(chat_id: int):
    await _exec("DELETE FROM music_queue WHERE chat_id=?", (chat_id,))
