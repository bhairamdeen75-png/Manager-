import time
from datetime import datetime, timedelta, timezone

from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin
from handlers.logs import log_action

_UNMUTED_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
)
_MUTED_PERMISSIONS = ChatPermissions(can_send_messages=False)

# In-memory state (resets on restart — fine, raids are a live/runtime concern)
_join_log: dict[int, list[float]] = {}                 # chat_id -> [join timestamps]
_locked_chats: set[int] = set()                          # chat_id currently hard-locked by raid mode
_slowmode_until: dict[int, float] = {}                    # chat_id -> epoch time until soft slow-mode applies
_last_message_time: dict[tuple[int, int], float] = {}    # (chat_id, user_id) -> last message epoch time


def _lock_job_name(chat_id: int) -> str:
    return f"raid_unlock_{chat_id}"


# ---------------- Commands ----------------

async def cmd_raidprotection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args or context.args[0].lower() not in ("on", "off"):
        s = db.get_raid_settings(update.effective_chat.id)
        await update.message.reply_text(
            "Use karo: /raidprotection on|off\n\n"
            f"Current: {s['threshold']} joins / {s['window']}s se lock trigger hoga, "
            f"{s['lock_minutes']} minute lock, uske baad {s['slowmode_after_minutes']} min ka soft slow-mode "
            f"({s['slowmode_seconds']}s/message).\n"
            "Thresholds badalne ke liye: /setraidlimits <joins> <seconds> <lock_minutes>"
        )
        return
    enabled = context.args[0].lower() == "on"
    db.set_raid_protection(update.effective_chat.id, enabled)
    state = "ON ✅" if enabled else "OFF ❌"
    await update.message.reply_text(f"🛡️ Raid protection: {state}")


async def cmd_setraidlimits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if len(context.args) != 3:
        await update.message.reply_text("Use karo: /setraidlimits <joins> <seconds> <lock_minutes>\nJaise: /setraidlimits 5 15 10")
        return
    try:
        joins, seconds, lock_minutes = (int(x) for x in context.args)
    except ValueError:
        await update.message.reply_text("Sab values numbers me do.")
        return
    db.set_raid_thresholds(update.effective_chat.id, threshold=joins, window=seconds, lock_minutes=lock_minutes)
    await update.message.reply_text(
        f"✅ Raid limits set: {joins} joins / {seconds}s → {lock_minutes} minute lock."
    )


async def cmd_lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/lock — group ko manually lock karo (sirf admins message bhej sakte hain)."""
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.set_chat_permissions(chat_id, _MUTED_PERMISSIONS)
    except Exception:
        await update.message.reply_text("❌ Lock nahi kar paya — bot ko 'restrict members' permission chahiye.")
        return
    _locked_chats.add(chat_id)
    await update.message.reply_text("🔒 Group lock kar diya gaya. Sirf admins ab message bhej sakte hain.")


async def cmd_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    chat_id = update.effective_chat.id
    for job in context.job_queue.get_jobs_by_name(_lock_job_name(chat_id)):
        job.schedule_removal()
    await _do_unlock(context, chat_id, notify=True)


# ---------------- Raid detection (called on every new_chat_members event) ----------------

async def check_raid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Logs joins and triggers a lockdown if too many happen too fast.
    Returns True if a raid was just triggered (caller can decide to skip captcha etc. for this batch)."""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return False
    if not db.get_raid_protection(chat.id):
        return False
    if chat.id in _locked_chats:
        return False  # already locked, nothing more to do

    settings = db.get_raid_settings(chat.id)
    now = time.time()
    new_members = [m for m in update.effective_message.new_chat_members if not m.is_bot]
    if not new_members:
        return False

    log = _join_log.setdefault(chat.id, [])
    log.extend([now] * len(new_members))
    cutoff = now - settings["window"]
    _join_log[chat.id] = [t for t in log if t >= cutoff]

    if len(_join_log[chat.id]) < settings["threshold"]:
        return False

    # Raid detected → hard lock the group
    _join_log[chat.id] = []
    _locked_chats.add(chat.id)
    try:
        await context.bot.set_chat_permissions(chat.id, _MUTED_PERMISSIONS)
    except Exception:
        pass

    await context.bot.send_message(
        chat.id,
        f"🚨 <b>Raid detected!</b> {len(new_members)}+ members ne thode second me join kiya.\n"
        f"🔒 Group {settings['lock_minutes']} minute ke liye auto-lock kar diya gaya (sirf admins likh sakte hain).\n"
        f"Admin chaho to /unlock se pehle bhi khol sakte ho.",
        parse_mode="HTML",
    )
    await log_action(
        context, chat.id,
        f"🚨 Raid protection triggered — group locked for {settings['lock_minutes']} min "
        f"({len(new_members)} joins in {settings['window']}s)."
    )

    context.job_queue.run_once(
        _auto_unlock,
        settings["lock_minutes"] * 60,
        chat_id=chat.id,
        name=_lock_job_name(chat.id),
        data={"chat_id": chat.id},
    )
    return True


async def _auto_unlock(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    await _do_unlock(context, chat_id, notify=True)


async def _do_unlock(context: ContextTypes.DEFAULT_TYPE, chat_id: int, notify: bool):
    _locked_chats.discard(chat_id)
    try:
        await context.bot.set_chat_permissions(chat_id, _UNMUTED_PERMISSIONS)
    except Exception:
        pass

    settings = db.get_raid_settings(chat_id)
    _slowmode_until[chat_id] = time.time() + settings["slowmode_after_minutes"] * 60

    if notify:
        try:
            await context.bot.send_message(
                chat_id,
                f"🔓 Group unlock kar diya gaya. Agle {settings['slowmode_after_minutes']} minute tak "
                f"soft slow-mode rahega (har user {settings['slowmode_seconds']}s me ek message).",
            )
        except Exception:
            pass


# ---------------- Soft slow-mode enforcement (Bot API has no native slow-mode setter,
# so this enforces a minimum gap between a user's messages at the application level) ----------------

async def enforce_slowmode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Returns True if the message was deleted for violating soft slow-mode."""
    chat = update.effective_chat
    msg = update.effective_message
    user = update.effective_user

    if not msg or chat.type not in ("group", "supergroup"):
        return False
    until = _slowmode_until.get(chat.id)
    if not until or time.time() > until:
        return False
    if await is_admin(update, context):
        return False

    settings = db.get_raid_settings(chat.id)
    key = (chat.id, user.id)
    now = time.time()
    last = _last_message_time.get(key, 0)

    if now - last < settings["slowmode_seconds"]:
        try:
            await msg.delete()
        except Exception:
            pass
        return True

    _last_message_time[key] = now
    return False
