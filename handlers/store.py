"""Naye features ka data store — Turso ke alag tables, database.py ke core tables ko touch nahi karta.

Same shared Turso connection database.py wala hi use karta hai (naya connection nahi banata).
Saare functions async hain — call karte waqt await lagao."""

import json
from datetime import datetime, timedelta, timezone

from database import _query, _exec, _cache_get, _cache_set, _cache_drop


def _now():
    return datetime.now(timezone.utc)


def init_store_tables():
    """Saari extra tables (agar exist nahi karti) bana deta hai. Startup pe (event
    loop shuru hone se pehle) sync call hoti hai — safe hai."""
    from database import _exec_sync_startup as _x
    _x("""CREATE TABLE IF NOT EXISTS approved_users (
        chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, name TEXT,
        PRIMARY KEY (chat_id, user_id))""")
    _x("""CREATE TABLE IF NOT EXISTS aliases (
        chat_id INTEGER NOT NULL, alias TEXT NOT NULL, target TEXT,
        PRIMARY KEY (chat_id, alias))""")
    _x("""CREATE TABLE IF NOT EXISTS invite_links (
        link TEXT PRIMARY KEY, chat_id INTEGER, inviter_id INTEGER)""")
    _x("""CREATE TABLE IF NOT EXISTS invites (
        chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, name TEXT, count INTEGER DEFAULT 0,
        PRIMARY KEY (chat_id, user_id))""")
    _x("""CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL,
        run_at TEXT NOT NULL, text TEXT, added_by INTEGER, created TEXT)""")
    _x("""CREATE TABLE IF NOT EXISTS appeals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        name TEXT, reason TEXT, status TEXT DEFAULT 'pending', created TEXT)""")
    _x("""CREATE TABLE IF NOT EXISTS global_bans (
        user_id INTEGER PRIMARY KEY, reason TEXT, "by" INTEGER, at TEXT)""")
    _x("""CREATE TABLE IF NOT EXISTS bans_log (
        chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, banned_at TEXT,
        PRIMARY KEY (chat_id, user_id))""")
    _x("""CREATE TABLE IF NOT EXISTS activity (
        chat_id INTEGER NOT NULL, day TEXT NOT NULL, user_id INTEGER NOT NULL,
        name TEXT, count INTEGER DEFAULT 0, PRIMARY KEY (chat_id, day, user_id))""")
    _x("""CREATE TABLE IF NOT EXISTS extras_settings (
        chat_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT,
        PRIMARY KEY (chat_id, key))""")
    _x("""CREATE TABLE IF NOT EXISTS counting (
        chat_id INTEGER PRIMARY KEY, target INTEGER DEFAULT 0,
        last_user INTEGER, record INTEGER DEFAULT 0)""")
    _x("""CREATE TABLE IF NOT EXISTS reputation (
        chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, rep INTEGER DEFAULT 0,
        PRIMARY KEY (chat_id, user_id))""")
    _x("""CREATE TABLE IF NOT EXISTS pets (
        chat_id INTEGER PRIMARY KEY, name TEXT, hunger INTEGER DEFAULT 80, born TEXT)""")
    _x("""CREATE TABLE IF NOT EXISTS confession_links (
        user_id INTEGER PRIMARY KEY, group_id INTEGER)""")
    _x("""CREATE TABLE IF NOT EXISTS confession_counters (
        group_id INTEGER PRIMARY KEY, num INTEGER DEFAULT 0)""")


# ---------- Approved / trusted users (cached — spam/filter checks isse guard hote hain) ----------
async def is_approved(chat_id, user_id):
    key = ("approved", chat_id)
    cached = _cache_get(key)
    if cached is None:
        rows = await _query("SELECT user_id FROM approved_users WHERE chat_id=?", (chat_id,))
        cached = {r["user_id"] for r in rows}
        _cache_set(key, cached)
    return user_id in cached


async def add_approved(chat_id, user_id, name):
    await _exec(
        "INSERT INTO approved_users (chat_id, user_id, name) VALUES (?, ?, ?) "
        "ON CONFLICT(chat_id, user_id) DO UPDATE SET name = excluded.name",
        (chat_id, user_id, name),
    )
    _cache_drop(("approved", chat_id))


async def remove_approved(chat_id, user_id):
    await _exec("DELETE FROM approved_users WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    _cache_drop(("approved", chat_id))


async def get_approved(chat_id):
    return await _query("SELECT chat_id, user_id, name FROM approved_users WHERE chat_id=?", (chat_id,))


# ---------- Aliases ----------
async def set_alias(chat_id, alias, target):
    await _exec(
        "INSERT INTO aliases (chat_id, alias, target) VALUES (?, ?, ?) "
        "ON CONFLICT(chat_id, alias) DO UPDATE SET target = excluded.target",
        (chat_id, alias.lower().lstrip("/"), target.lower().lstrip("/")),
    )


async def del_alias(chat_id, alias):
    await _exec("DELETE FROM aliases WHERE chat_id=? AND alias=?", (chat_id, alias.lower().lstrip("/")))


async def get_aliases(chat_id):
    rows = await _query("SELECT alias, target FROM aliases WHERE chat_id=?", (chat_id,))
    return {r["alias"]: r["target"] for r in rows}


# ---------- Invite link map ----------
async def map_link_to_inviter(chat_id, link, inviter_id):
    await _exec(
        "INSERT INTO invite_links (link, chat_id, inviter_id) VALUES (?, ?, ?) "
        "ON CONFLICT(link) DO UPDATE SET chat_id = excluded.chat_id, inviter_id = excluded.inviter_id",
        (link, chat_id, inviter_id),
    )


async def set_inviter_name(chat_id, user_id, name):
    await _exec(
        "INSERT INTO invites (chat_id, user_id, name, count) VALUES (?, ?, ?, 0) "
        "ON CONFLICT(chat_id, user_id) DO UPDATE SET name = excluded.name",
        (chat_id, user_id, name),
    )


# ---------- Invite counts (leaderboard) ----------
async def get_invites(chat_id, user_id):
    rows = await _query("SELECT count FROM invites WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    return rows[0]["count"] if rows else 0


async def inc_invite(chat_id, inviter_id, name=""):
    rows = await _query("SELECT name FROM invites WHERE chat_id=? AND user_id=?", (chat_id, inviter_id))
    if rows:
        new_name = name or rows[0]["name"]
        await _exec(
            "UPDATE invites SET count = count + 1, name = ? WHERE chat_id=? AND user_id=?",
            (new_name, chat_id, inviter_id),
        )
    else:
        await _exec(
            "INSERT INTO invites (chat_id, user_id, name, count) VALUES (?, ?, ?, 1)",
            (chat_id, inviter_id, name or None),
        )


async def top_inviters(chat_id, limit=10):
    return await _query(
        "SELECT user_id, name, count FROM invites WHERE chat_id=? ORDER BY count DESC LIMIT ?",
        (chat_id, limit),
    )


# ---------- Scheduled messages ----------
async def add_schedule(chat_id, run_at, text, added_by):
    lastrowid = await _exec(
        "INSERT INTO schedules (chat_id, run_at, text, added_by, created) VALUES (?, ?, ?, ?, ?)",
        (chat_id, run_at.isoformat(), text, added_by, _now().isoformat()),
    )
    if lastrowid:
        return lastrowid
    rows = await _query(
        "SELECT id FROM schedules WHERE chat_id=? ORDER BY id DESC LIMIT 1", (chat_id,)
    )
    return rows[0]["id"] if rows else None


def _parse_dt(s):
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def get_schedules(chat_id):
    rows = await _query(
        "SELECT id, chat_id, run_at, text, added_by FROM schedules WHERE chat_id=? ORDER BY run_at",
        (chat_id,),
    )
    return [{**r, "_id": r["id"], "run_at": _parse_dt(r["run_at"])} for r in rows]


async def get_chat_schedules(chat_id):
    rows = await _query(
        "SELECT id, chat_id, run_at, text, added_by FROM schedules WHERE chat_id=?", (chat_id,)
    )
    return [{**r, "_id": r["id"], "run_at": _parse_dt(r["run_at"])} for r in rows]


async def del_schedule(chat_id, sched_id):
    try:
        sid = int(sched_id)
    except (TypeError, ValueError):
        return
    await _exec("DELETE FROM schedules WHERE id=? AND chat_id=?", (sid, chat_id))


async def all_pending_schedules():
    rows = await _query("SELECT id, chat_id, run_at, text, added_by FROM schedules")
    return [{**r, "_id": r["id"], "run_at": _parse_dt(r["run_at"])} for r in rows]


# ---------- extras_settings EAV helpers (cached snapshot, jaise database.py ki settings) ----------
async def _extras_snapshot(chat_id):
    key = ("extras", chat_id)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    rows = await _query("SELECT key, value FROM extras_settings WHERE chat_id=?", (chat_id,))
    snap = {r["key"]: (json.loads(r["value"]) if r["value"] is not None else None) for r in rows}
    _cache_set(key, snap)
    return snap


async def _get_extra(chat_id, key, default=None):
    snap = await _extras_snapshot(chat_id)
    val = snap.get(key, None)
    return default if val is None else val


async def _set_extra(chat_id, key, value):
    await _exec(
        "INSERT INTO extras_settings (chat_id, key, value) VALUES (?, ?, ?) "
        "ON CONFLICT(chat_id, key) DO UPDATE SET value = excluded.value",
        (chat_id, key, json.dumps(value)),
    )
    _cache_drop(("extras", chat_id))


async def _unset_extra(chat_id, key):
    await _exec("DELETE FROM extras_settings WHERE chat_id=? AND key=?", (chat_id, key))
    _cache_drop(("extras", chat_id))


# ---------- Spam threshold ----------
async def get_spam_threshold(chat_id):
    val = await _get_extra(chat_id, "spam_threshold")
    return val if val is not None else 8


async def set_spam_threshold(chat_id, val):
    await _set_extra(chat_id, "spam_threshold", val)


# ---------- Captcha mode ----------
async def get_captcha_mode(chat_id):
    val = await _get_extra(chat_id, "captcha_mode")
    return val if val is not None else "math"


async def set_captcha_mode(chat_id, mode):
    await _set_extra(chat_id, "captcha_mode", mode)


# ---------- Welcome media (standalone keys, pehle wale welcome.* se alag) ----------
async def set_welcome_media(chat_id, file_id, mtype):
    await _set_extra(chat_id, "welcome_media", {"file_id": file_id, "type": mtype})


async def get_welcome_media(chat_id):
    return await _get_extra(chat_id, "welcome_media", None)


async def clear_welcome_media(chat_id):
    await _unset_extra(chat_id, "welcome_media")


async def set_welcome_buttons(chat_id, buttons):
    await _set_extra(chat_id, "welcome_buttons", buttons)


async def get_welcome_buttons(chat_id):
    return await _get_extra(chat_id, "welcome_buttons", [])


async def clear_welcome_buttons(chat_id):
    await _unset_extra(chat_id, "welcome_buttons")


# ---------- Appeals ----------
async def add_appeal(chat_id, user_id, name, reason):
    await _exec(
        "INSERT INTO appeals (chat_id, user_id, name, reason, status, created) "
        "VALUES (?, ?, ?, ?, 'pending', ?)",
        (chat_id, user_id, name, reason, _now().isoformat()),
    )


async def set_appeal_status(appeal_id, status):
    await _exec("UPDATE appeals SET status=? WHERE id=?", (status, appeal_id))


async def get_open_appeals(user_id):
    return await _query("SELECT * FROM appeals WHERE user_id=? AND status='pending'", (user_id,))


# ---------- Global ban (cached — har message pe check hota hai) ----------
async def _gban_snapshot():
    key = ("gban", "all")
    cached = _cache_get(key)
    if cached is not None:
        return cached
    rows = await _query("SELECT user_id, reason FROM global_bans")
    snap = {r["user_id"]: r["reason"] for r in rows}
    _cache_set(key, snap)
    return snap


async def gban_add(user_id, reason, by):
    await _exec(
        'INSERT INTO global_bans (user_id, reason, "by", at) VALUES (?, ?, ?, ?) '
        'ON CONFLICT(user_id) DO UPDATE SET reason = excluded.reason, "by" = excluded."by", '
        'at = excluded.at',
        (user_id, reason, by, _now().isoformat()),
    )
    _cache_drop(("gban", "all"))


async def gban_remove(user_id):
    await _exec("DELETE FROM global_bans WHERE user_id=?", (user_id,))
    _cache_drop(("gban", "all"))


async def is_gbanned(user_id):
    snap = await _gban_snapshot()
    if user_id in snap:
        return {"user_id": user_id, "reason": snap[user_id]}
    return None


async def gban_list():
    return await _query("SELECT user_id, reason FROM global_bans")

# ---------- Activity (daily message counts) ----------
async def bump_activity(chat_id, user_id):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await _exec(
        "INSERT INTO activity (chat_id, day, user_id, name, count) VALUES (?, ?, ?, NULL, 1) "
        "ON CONFLICT(chat_id, day, user_id) DO UPDATE SET count = count + 1",
        (chat_id, today, user_id),
    )


async def get_activity(chat_id, days=7):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    return await _query(
        "SELECT chat_id, day, user_id, name, count FROM activity WHERE chat_id=? AND day>=?",
        (chat_id, since),
    )


# ---------- Counting game ----------
async def get_count_target(chat_id):
    rows = await _query("SELECT target FROM counting WHERE chat_id=?", (chat_id,))
    return rows[0]["target"] if rows else 0


async def set_count_target(chat_id, val):
    await _exec(
        "INSERT INTO counting (chat_id, target) VALUES (?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET target = excluded.target",
        (chat_id, val),
    )


async def get_count_last_user(chat_id):
    rows = await _query("SELECT last_user FROM counting WHERE chat_id=?", (chat_id,))
    return rows[0]["last_user"] if rows else None


async def set_count_last_user(chat_id, user_id):
    await _exec(
        "INSERT INTO counting (chat_id, last_user) VALUES (?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET last_user = excluded.last_user",
        (chat_id, user_id),
    )


async def get_count_record(chat_id):
    rows = await _query("SELECT record FROM counting WHERE chat_id=?", (chat_id,))
    return rows[0]["record"] if rows else 0


async def set_count_record(chat_id, val):
    await _exec(
        "INSERT INTO counting (chat_id, record) VALUES (?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET record = excluded.record",
        (chat_id, val),
    )


# ---------- Reputation ----------
async def get_rep(chat_id, user_id):
    rows = await _query("SELECT rep FROM reputation WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    return rows[0]["rep"] if rows else 0


async def change_rep(chat_id, user_id, delta):
    await _exec(
        "INSERT INTO reputation (chat_id, user_id, rep) VALUES (?, ?, ?) "
        "ON CONFLICT(chat_id, user_id) DO UPDATE SET rep = rep + ?",
        (chat_id, user_id, delta, delta),
    )
    return await get_rep(chat_id, user_id)


# ---------- Virtual pet ----------
async def get_pet(chat_id):
    rows = await _query("SELECT chat_id, name, hunger, born FROM pets WHERE chat_id=?", (chat_id,))
    return rows[0] if rows else None


async def init_pet(chat_id, name):
    await _exec(
        "INSERT INTO pets (chat_id, name, hunger, born) VALUES (?, ?, 80, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET name = excluded.name, hunger = 80, born = excluded.born",
        (chat_id, name, _now().isoformat()),
    )


async def update_pet_hunger(chat_id, hunger):
    await _exec(
        "INSERT INTO pets (chat_id, hunger) VALUES (?, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET hunger = excluded.hunger",
        (chat_id, hunger),
    )


# ---------- Confessions ----------
async def set_confession_group(user_id, group_id):
    await _exec(
        "INSERT INTO confession_links (user_id, group_id) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET group_id = excluded.group_id",
        (user_id, group_id),
    )


async def get_confession_group(user_id):
    rows = await _query("SELECT group_id FROM confession_links WHERE user_id=?", (user_id,))
    return rows[0]["group_id"] if rows else None


async def next_confession_num(group_id):
    rows = await _query("SELECT num FROM confession_counters WHERE group_id=?", (group_id,))
    current = rows[0]["num"] if rows else 0
    await _exec(
        "INSERT INTO confession_counters (group_id, num) VALUES (?, ?) "
        "ON CONFLICT(group_id) DO UPDATE SET num = excluded.num",
        (group_id, current + 1),
    )
    return current + 1


# ---------- Autoreact ----------
async def set_autoreact(chat_id, enabled: bool):
    await _set_extra(chat_id, "autoreact", bool(enabled))


async def get_autoreact(chat_id) -> bool:
    return bool(await _get_extra(chat_id, "autoreact", False))
