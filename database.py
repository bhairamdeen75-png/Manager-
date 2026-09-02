"""MongoDB data layer for the bot (via pymongo).

All functions keep the exact same names/signatures as the earlier SQLite
version, so none of the handler files need to change — only the storage
engine underneath changed.
"""

import time
import logging

from pymongo import MongoClient, ASCENDING
from pymongo.errors import ServerSelectionTimeoutError

from config import MONGO_URI, MONGO_DB_NAME

logger = logging.getLogger(__name__)

_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
_db = _client[MONGO_DB_NAME]

warns_col = _db["warns"]
filters_col = _db["filters"]
settings_col = _db["settings"]
notes_col = _db["notes"]
auto_responses_col = _db["auto_responses"]
xp_col = _db["xp"]
seen_users_col = _db["seen_users"]
stats_col = _db["stats"]
groups_col = _db["groups"]


def init_db():
    """Verifies the MongoDB connection and (re)creates indexes. Safe to call
    every startup — index creation is a no-op if the index already exists."""
    try:
        _client.admin.command("ping")
    except ServerSelectionTimeoutError as e:
        raise SystemExit(
            f"❌ MongoDB se connect nahi ho paya ({MONGO_URI}). "
            f"MONGO_URI env var check karo. Error: {e}"
        )

    warns_col.create_index([("chat_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
    filters_col.create_index([("chat_id", ASCENDING), ("word", ASCENDING)], unique=True)
    settings_col.create_index([("chat_id", ASCENDING)], unique=True)
    notes_col.create_index([("chat_id", ASCENDING), ("name", ASCENDING)], unique=True)
    auto_responses_col.create_index([("chat_id", ASCENDING), ("trigger", ASCENDING)], unique=True)
    xp_col.create_index([("chat_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
    seen_users_col.create_index([("chat_id", ASCENDING), ("user_id", ASCENDING)], unique=True)
    stats_col.create_index([("chat_id", ASCENDING)], unique=True)
    groups_col.create_index([("chat_id", ASCENDING)], unique=True)

    logger.info("MongoDB connected (%s / %s)", MONGO_URI, MONGO_DB_NAME)


# ---------------- Warns ----------------

def add_warn(chat_id: int, user_id: int) -> int:
    doc = warns_col.find_one_and_update(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"count": 1}},
        upsert=True,
        return_document=True,
    )
    return doc["count"] if doc else 1


def get_warns(chat_id: int, user_id: int) -> int:
    doc = warns_col.find_one({"chat_id": chat_id, "user_id": user_id})
    return doc["count"] if doc else 0


def reset_warns(chat_id: int, user_id: int):
    warns_col.delete_one({"chat_id": chat_id, "user_id": user_id})


# ---------------- Filters ----------------

def add_filter(chat_id: int, word: str):
    filters_col.update_one(
        {"chat_id": chat_id, "word": word.lower()},
        {"$setOnInsert": {"chat_id": chat_id, "word": word.lower()}},
        upsert=True,
    )


def remove_filter(chat_id: int, word: str):
    filters_col.delete_one({"chat_id": chat_id, "word": word.lower()})


def get_filters(chat_id: int):
    return [doc["word"] for doc in filters_col.find({"chat_id": chat_id})]


# ---------------- Settings: welcome ----------------

def set_welcome(chat_id: int, text: str):
    _set_setting(chat_id, "welcome_text", text)


def get_welcome(chat_id: int):
    return _get_setting(chat_id, "welcome_text", None)


# ---------------- Settings: generic helpers ----------------

def _get_setting(chat_id: int, field: str, default=None):
    doc = settings_col.find_one({"chat_id": chat_id}, {field: 1})
    if not doc or field not in doc or doc[field] is None:
        return default
    return doc[field]


def _set_setting(chat_id: int, field: str, value):
    settings_col.update_one(
        {"chat_id": chat_id}, {"$set": {field: value}}, upsert=True
    )


# ---------------- Link / username blocker ----------------

def set_link_block(chat_id: int, enabled: bool):
    _set_setting(chat_id, "link_block", bool(enabled))


def get_link_block(chat_id: int) -> bool:
    return bool(_get_setting(chat_id, "link_block", False))


# ---------------- Media restriction ----------------

def set_media_restrict(chat_id: int, types_csv: str):
    _set_setting(chat_id, "media_restrict", types_csv)


def get_media_restrict(chat_id: int):
    val = _get_setting(chat_id, "media_restrict", "") or ""
    return [t for t in val.split(",") if t]


# ---------------- Admin log channel ----------------

def set_log_channel(chat_id: int, log_channel_id):
    _set_setting(chat_id, "log_channel_id", log_channel_id)


def get_log_channel(chat_id: int):
    return _get_setting(chat_id, "log_channel_id", None)


# ---------------- Night mode ----------------

def set_night_mode(chat_id: int, enabled: bool):
    _set_setting(chat_id, "night_mode", bool(enabled))


def get_night_mode(chat_id: int) -> bool:
    return bool(_get_setting(chat_id, "night_mode", False))


def set_night_time(chat_id: int, start: str, end: str):
    settings_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"night_start": start, "night_end": end}},
        upsert=True,
    )


def get_night_time(chat_id: int):
    start = _get_setting(chat_id, "night_start", "23:00")
    end = _get_setting(chat_id, "night_end", "06:00")
    return start, end


def get_all_night_mode_chats():
    docs = settings_col.find(
        {"night_mode": True}, {"chat_id": 1, "night_start": 1, "night_end": 1}
    )
    return [
        {
            "chat_id": d["chat_id"],
            "night_start": d.get("night_start", "23:00"),
            "night_end": d.get("night_end", "06:00"),
        }
        for d in docs
    ]


# ---------------- Rules / accept gate ----------------

def set_rules(chat_id: int, text: str):
    _set_setting(chat_id, "rules_text", text)


def get_rules(chat_id: int):
    return _get_setting(chat_id, "rules_text", None)


def set_rules_gate(chat_id: int, enabled: bool):
    _set_setting(chat_id, "rules_gate", bool(enabled))


def get_rules_gate(chat_id: int) -> bool:
    return bool(_get_setting(chat_id, "rules_gate", False))


# ---------------- Auto-delete join/leave ----------------

def set_autodelete_joinleave(chat_id: int, enabled: bool):
    _set_setting(chat_id, "autodelete_joinleave", bool(enabled))


def get_autodelete_joinleave(chat_id: int) -> bool:
    return bool(_get_setting(chat_id, "autodelete_joinleave", False))


# ---------------- Auto-pin ----------------

def set_autopin(chat_id: int, enabled: bool):
    _set_setting(chat_id, "autopin", bool(enabled))


def get_autopin(chat_id: int) -> bool:
    return bool(_get_setting(chat_id, "autopin", False))


# ---------------- Raid protection / slow-mode ----------------

def set_raid_protection(chat_id: int, enabled: bool):
    _set_setting(chat_id, "raid_protection", bool(enabled))


def get_raid_protection(chat_id: int) -> bool:
    default_doc = settings_col.find_one({"chat_id": chat_id}, {"raid_protection": 1})
    if not default_doc or "raid_protection" not in default_doc:
        return True  # on by default, matches previous SQLite DEFAULT 1
    return bool(default_doc["raid_protection"])


def get_raid_settings(chat_id: int):
    doc = settings_col.find_one({"chat_id": chat_id}) or {}
    return {
        "threshold": int(doc.get("raid_join_threshold", 5)),
        "window": int(doc.get("raid_time_window", 15)),
        "lock_minutes": int(doc.get("raid_lock_minutes", 10)),
        "slowmode_seconds": int(doc.get("slowmode_seconds", 8)),
        "slowmode_after_minutes": int(doc.get("slowmode_after_minutes", 15)),
    }


def set_raid_thresholds(chat_id: int, threshold: int = None, window: int = None, lock_minutes: int = None):
    update = {}
    if threshold is not None:
        update["raid_join_threshold"] = threshold
    if window is not None:
        update["raid_time_window"] = window
    if lock_minutes is not None:
        update["raid_lock_minutes"] = lock_minutes
    if update:
        settings_col.update_one({"chat_id": chat_id}, {"$set": update}, upsert=True)


# ---------------- Notes (#hashtag) ----------------

def add_note(chat_id: int, name: str, content: str):
    notes_col.update_one(
        {"chat_id": chat_id, "name": name.lower()},
        {"$set": {"content": content}},
        upsert=True,
    )


def remove_note(chat_id: int, name: str):
    notes_col.delete_one({"chat_id": chat_id, "name": name.lower()})


def get_note(chat_id: int, name: str):
    doc = notes_col.find_one({"chat_id": chat_id, "name": name.lower()})
    return doc["content"] if doc else None


def list_notes(chat_id: int):
    docs = notes_col.find({"chat_id": chat_id}).sort("name", ASCENDING)
    return [d["name"] for d in docs]


# ---------------- Custom auto-responses ----------------

def add_response(chat_id: int, trigger: str, response: str):
    auto_responses_col.update_one(
        {"chat_id": chat_id, "trigger": trigger.lower()},
        {"$set": {"response": response}},
        upsert=True,
    )


def remove_response(chat_id: int, trigger: str):
    auto_responses_col.delete_one({"chat_id": chat_id, "trigger": trigger.lower()})


def list_responses(chat_id: int):
    docs = auto_responses_col.find({"chat_id": chat_id}).sort("trigger", ASCENDING)
    return [{"trigger": d["trigger"], "response": d["response"]} for d in docs]


# ---------------- XP + leaderboard ----------------

def add_xp(chat_id: int, user_id: int, amount: int, cooldown_seconds: int = 30):
    """Adds XP if the user is outside their cooldown window. Returns new total, or
    None if the award was skipped because the user is still on cooldown."""
    now = time.time()
    existing = xp_col.find_one({"chat_id": chat_id, "user_id": user_id})
    if existing and (now - existing.get("last_xp_time", 0)) < cooldown_seconds:
        return None

    new_xp = (existing["xp"] if existing else 0) + amount
    xp_col.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"xp": new_xp, "last_xp_time": now}},
        upsert=True,
    )
    return new_xp


def get_xp(chat_id: int, user_id: int) -> int:
    doc = xp_col.find_one({"chat_id": chat_id, "user_id": user_id})
    return doc["xp"] if doc else 0


def get_leaderboard(chat_id: int, limit: int = 10):
    docs = xp_col.find({"chat_id": chat_id}).sort("xp", -1).limit(limit)
    return [{"user_id": d["user_id"], "xp": d["xp"]} for d in docs]


def get_xp_chats():
    """Saare groups jinhone kabhi XP kamaya hai — hourly leaderboard post ke liye."""
    return [c for c in xp_col.distinct("chat_id") if c > 0]

# ---------------- Seen users (for /tagall) ----------------

def track_user(chat_id: int, user_id: int, username: str, first_name: str):
    seen_users_col.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"username": username, "first_name": first_name}},
        upsert=True,
    )


def get_seen_users(chat_id: int):
    docs = seen_users_col.find({"chat_id": chat_id})
    return [
        {"user_id": d["user_id"], "username": d.get("username", ""), "first_name": d.get("first_name", "")}
        for d in docs
    ]


def remove_seen_user(chat_id: int, user_id: int):
    seen_users_col.delete_one({"chat_id": chat_id, "user_id": user_id})


# ---------------- Stats ----------------

def increment_message_count(chat_id: int):
    stats_col.update_one(
        {"chat_id": chat_id},
        {"$inc": {"total_messages": 1}, "$setOnInsert": {"commands_used": 0}},
        upsert=True,
    )


def increment_command_count(chat_id: int):
    stats_col.update_one(
        {"chat_id": chat_id},
        {"$inc": {"commands_used": 1}, "$setOnInsert": {"total_messages": 0}},
        upsert=True,
    )


def get_stats(chat_id: int):
    doc = stats_col.find_one({"chat_id": chat_id})
    if not doc:
        return {"total_messages": 0, "commands_used": 0}
    return {
        "total_messages": doc.get("total_messages", 0),
        "commands_used": doc.get("commands_used", 0),
    }


# ---------------- Groups registry (for panel: My Groups / Owner Panel) ----------------

def track_group(chat_id: int, title: str):
    """Called whenever the bot sees activity in a group, so we know which
    groups it's currently active in (used by the /start button panel)."""
    groups_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"title": title}},
        upsert=True,
    )


def remove_group(chat_id: int):
    """Called when the bot is removed/kicked from a group."""
    groups_col.delete_one({"chat_id": chat_id})


def get_all_groups():
    docs = groups_col.find({})
    return [{"chat_id": d["chat_id"], "title": d.get("title", "Unknown Group")} for d in docs]


def get_group_count() -> int:
    return groups_col.count_documents({})


def get_bot_wide_stats():
    """Aggregate counters for the owner panel."""
    total_groups = groups_col.count_documents({})
    total_users = len(seen_users_col.distinct("user_id"))
    pipeline = [
        {"$group": {"_id": None, "messages": {"$sum": "$total_messages"}, "commands": {"$sum": "$commands_used"}}}
    ]
    agg = list(stats_col.aggregate(pipeline))
    total_messages = agg[0]["messages"] if agg else 0
    total_commands = agg[0]["commands"] if agg else 0
    return {
        "groups": total_groups,
        "users": total_users,
        "messages": total_messages,
        "commands": total_commands,
    }

# ---------------- Leave message ----------------

def set_leave_message(chat_id: int, text: str):
    settings_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"leave_msg": text}},
        upsert=True,
    )


def get_leave_message(chat_id: int):
    doc = settings_col.find_one({"chat_id": chat_id})
    return doc.get("leave_msg") if doc else None

def export_group_data(chat_id):
    """Saare collections se is group ka data nikaalo."""
    out = {}
    for name, coll in [
        ("notes", notes_col), ("filters", filters_col),
        ("warns", warns_col), ("settings", settings_col),
    ]:
        docs = list(coll.find({"chat_id": chat_id}, {"_id": 0}))
        if docs:
            out[name] = docs
    return out


def import_group_data(chat_id, data):
    """JSON backup ko is group me import karo (existing overwrite)."""
    count = 0
    for name, docs in data.items():
        coll = {"notes": notes_col, "filters": filters_col,
                "warns": warns_col, "settings": settings_col}[name]
        coll.delete_many({"chat_id": chat_id})
        for doc in docs:
            doc["chat_id"] = chat_id
            coll.insert_one(doc)
            count += 1
    return count

# ---------------- Anti-forward ----------------

def set_antiforward(chat_id: int, enabled: bool):
    settings_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"antiforward": enabled}},
        upsert=True,
    )


def get_antiforward(chat_id: int) -> bool:
    doc = settings_col.find_one({"chat_id": chat_id})
    return doc.get("antiforward", False) if doc else False

# ---------------- Guess game (restart-proof) ----------------

def set_guess_game(chat_id: int, number: int):
    stats_col.database["guess_games"].update_one(
        {"chat_id": chat_id},
        {"$set": {"number": number, "tries": 0}},
        upsert=True,
    )


def get_guess_game(chat_id: int):
    doc = stats_col.database["guess_games"].find_one({"chat_id": chat_id})
    if not doc:
        return None
    return {"number": doc["number"], "tries": doc.get("tries", 0)}


def add_guess_try(chat_id: int):
    stats_col.database["guess_games"].update_one(
        {"chat_id": chat_id}, {"$inc": {"tries": 1}}
    )


def delete_guess_game(chat_id: int):
    stats_col.database["guess_games"].delete_one({"chat_id": chat_id})

