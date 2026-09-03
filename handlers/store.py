"""Naye features ka data store — alag collections, database.py ko touch nahi karta."""

from datetime import datetime, timedelta, timezone
from pymongo import MongoClient

from config import MONGO_URI, MONGO_DB_NAME

_client = MongoClient(MONGO_URI)
_db = _client[MONGO_DB_NAME]

approved = _db["approved_users"]
aliases = _db["aliases"]
invites = _db["invites"]
schedules = _db["schedules"]
appeals = _db["appeals"]
gbans = _db["global_bans"]
activity = _db["activity"]
bans_log = _db["bans_log"]
settings = _db["extras_settings"]
globalbans = _db["global_bans"]


def _now():
    return datetime.now(timezone.utc)


# ---------- Approved / trusted users ----------
def is_approved(chat_id, user_id):
    return approved.find_one({"chat_id": chat_id, "user_id": user_id}) is not None

def add_approved(chat_id, user_id, name):
    approved.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"chat_id": chat_id, "user_id": user_id, "name": name,
                  "by": None, "at": _now()}},
        upsert=True,
    )

def remove_approved(chat_id, user_id):
    approved.delete_one({"chat_id": chat_id, "user_id": user_id})

def get_approved(chat_id):
    return list(approved.find({"chat_id": chat_id}))


# ---------- Aliases ----------
def set_alias(chat_id, alias, target):
    aliases.update_one(
        {"chat_id": chat_id, "alias": alias.lower().lstrip("/")},
        {"$set": {"target": target.lower().lstrip("/")}},
        upsert=True,
    )

def del_alias(chat_id, alias):
    aliases.delete_one({"chat_id": chat_id, "alias": alias.lower().lstrip("/")})

def get_aliases(chat_id):
    return {a["alias"]: a["target"] for a in aliases.find({"chat_id": chat_id})}


# ---------- Invite link map ----------
linkmap = _db["invite_links"]

def map_link_to_inviter(chat_id, link, inviter_id):
    linkmap.update_one(
        {"link": link},
        {"$set": {"chat_id": chat_id, "inviter_id": inviter_id}},
        upsert=True,
    )

def set_inviter_name(chat_id, user_id, name):
    invites.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"name": name}},
        upsert=True,
    )


# ---------- Scheduled messages ----------
def add_schedule(chat_id, run_at, text, added_by):
    return schedules.insert_one(
        {"chat_id": chat_id, "run_at": run_at, "text": text,
         "added_by": added_by, "created": _now()}
    ).inserted_id

def get_schedules(chat_id):
    return list(schedules.find({"chat_id": chat_id}).sort("run_at", 1))

def get_chat_schedules(chat_id):
    return list(schedules.find({"chat_id": chat_id}))

def del_schedule(chat_id, sched_id):
    from bson import ObjectId
    schedules.delete_one({"_id": ObjectId(sched_id), "chat_id": chat_id})

def all_pending_schedules():
    return list(schedules.find({}))


# ---------- Spam threshold ----------
def get_spam_threshold(chat_id):
    doc = settings.find_one({"chat_id": chat_id})
    return doc.get("spam_threshold", 8) if doc else 8

def set_spam_threshold(chat_id, val):
    settings.update_one({"chat_id": chat_id}, {"$set": {"spam_threshold": val}}, upsert=True)


# ---------- Captcha mode ----------
def get_captcha_mode(chat_id):
    doc = settings.find_one({"chat_id": chat_id})
    return doc.get("captcha_mode", "math") if doc else "math"

def set_captcha_mode(chat_id, mode):
    settings.update_one({"chat_id": chat_id}, {"$set": {"captcha_mode": mode}}, upsert=True)



# ---------- Welcome media (standalone keys, pehle wale welcome.* se alag) ----------
def set_welcome_media(chat_id, file_id, mtype):
    settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"welcome_media": {"file_id": file_id, "type": mtype}}},
        upsert=True,
    )

def get_welcome_media(chat_id):
    doc = settings.find_one({"chat_id": chat_id})
    return doc.get("welcome_media") if doc else None

def clear_welcome_media(chat_id):
    settings.update_one({"chat_id": chat_id}, {"$unset": {"welcome_media": ""}})

def set_welcome_buttons(chat_id, buttons):
    settings.update_one(
        {"chat_id": chat_id},
        {"$set": {"welcome_buttons": buttons}},
        upsert=True,
    )

def get_welcome_buttons(chat_id):
    doc = settings.find_one({"chat_id": chat_id})
    return doc.get("welcome_buttons", []) if doc else []

def clear_welcome_buttons(chat_id):
    settings.update_one({"chat_id": chat_id}, {"$unset": {"welcome_buttons": ""}})

# ---------- Appeals ----------
def add_appeal(chat_id, user_id, name, reason):
    appeals.insert_one({"chat_id": chat_id, "user_id": user_id, "name": name,
                        "reason": reason, "status": "pending", "created": _now()})

def set_appeal_status(appeal_id, status):
    appeals.update_one({"_id": appeal_id}, {"$set": {"status": status}})

def get_open_appeals(user_id):
    return list(appeals.find({"user_id": user_id, "status": "pending"}))


# ---------- Global ban ----------
def gban_add(user_id, reason, by):
    globalbans.update_one({"user_id": user_id},
                          {"$set": {"reason": reason, "by": by, "at": _now()}}, upsert=True)

def gban_remove(user_id):
    globalbans.delete_one({"user_id": user_id})

def is_gbanned(user_id):
    return globalbans.find_one({"user_id": user_id})

def gban_list():
    return list(globalbans.find({}))


# ---------- Ban log (appeals ke liye) ----------
def record_ban(chat_id, user_id):
    bans_log.update_one({"chat_id": chat_id, "user_id": user_id},
                        {"$set": {"banned_at": _now()}}, upsert=True)

def get_ban_group(user_id):
    doc = bans_log.find_one({"user_id": user_id}, sort=[("banned_at", -1)])
    return doc["chat_id"] if doc else None


# ---------- Activity (daily message counts) ----------
def bump_activity(chat_id, user_id):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    activity.update_one(
        {"chat_id": chat_id, "day": today, "user_id": user_id},
        {"$inc": {"count": 1}, "$set": {"name": None}}, upsert=True,
    )

def get_activity(chat_id, days=7):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    return list(activity.find({"chat_id": chat_id, "day": {"$gte": since}}))


# ---------- Counting game ----------
counts = _db["counting"]

def get_count_target(chat_id):
    doc = counts.find_one({"chat_id": chat_id})
    return doc.get("target", 0) if doc else 0

def set_count_target(chat_id, val):
    counts.update_one({"chat_id": chat_id}, {"$set": {"target": val}}, upsert=True)

def get_count_last_user(chat_id):
    doc = counts.find_one({"chat_id": chat_id})
    return doc.get("last_user") if doc else None

def set_count_last_user(chat_id, user_id):
    counts.update_one({"chat_id": chat_id}, {"$set": {"last_user": user_id}}, upsert=True)

def get_count_record(chat_id):
    doc = counts.find_one({"chat_id": chat_id})
    return doc.get("record", 0) if doc else 0

def set_count_record(chat_id, val):
    counts.update_one({"chat_id": chat_id}, {"$set": {"record": val}}, upsert=True)


# ---------- Reputation ----------
reps = _db["reputation"]

def get_rep(chat_id, user_id):
    doc = reps.find_one({"chat_id": chat_id, "user_id": user_id})
    return doc.get("rep", 0) if doc else 0

def change_rep(chat_id, user_id, delta):
    reps.update_one({"chat_id": chat_id, "user_id": user_id},
                    {"$inc": {"rep": delta}}, upsert=True)
    return get_rep(chat_id, user_id)


# ---------- Virtual pet ----------
pets = _db["pets"]

def get_pet(chat_id):
    return pets.find_one({"chat_id": chat_id})

def init_pet(chat_id, name):
    pets.update_one({"chat_id": chat_id},
                    {"$set": {"name": name, "hunger": 80, "born": __import__("datetime").datetime.now()}},
                    upsert=True)

def update_pet_hunger(chat_id, hunger):
    pets.update_one({"chat_id": chat_id}, {"$set": {"hunger": hunger}}, upsert=True)


# ---------- Confessions ----------
confessions = _db["confessions"]

def set_confession_group(user_id, group_id):
    confessions.update_one({"user_id": user_id}, {"$set": {"group_id": group_id}}, upsert=True)

def get_confession_group(user_id):
    doc = confessions.find_one({"user_id": user_id})
    return doc.get("group_id") if doc else None

def next_confession_num(group_id):
    doc = confessions.find_one({"group_id": group_id, "num": {"$exists": True}})
    current = doc.get("num", 0) if doc else 0
    confessions.update_one({"group_id": group_id},
                           {"$set": {"num": current + 1}}, upsert=True)
    return current + 1
    
# ---------- Autoreact ----------
def set_autoreact(chat_id, enabled: bool):
    settings.update_one(
        {"chat_id": chat_id}, {"$set": {"autoreact": enabled}}, upsert=True
    )

def get_autoreact(chat_id) -> bool:
    doc = settings.find_one({"chat_id": chat_id})
    return bool(doc.get("autoreact", False)) if doc else False

