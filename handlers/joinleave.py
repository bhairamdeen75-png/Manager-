import logging

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin, format_welcome_leave

logger = logging.getLogger(__name__)


def _parse_delay(arg: str):
    """'30' -> 30 sec, '5m' -> 300 sec, '2h' -> 7200 sec. None = invalid."""
    arg = arg.lower().strip()
    try:
        if arg.endswith("m"):
            return int(arg[:-1]) * 60
        if arg.endswith("h"):
            return int(arg[:-1]) * 3600
        return int(arg)
    except ValueError:
        return None


async def cmd_autodeletejoinleave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return

    if not context.args or context.args[0].lower() not in ("on", "off"):
        current = db.get_autodelete_joinleave(update.effective_chat.id)
        delay = db.get_autodelete_delay(update.effective_chat.id)
        state = "ON ✅" if current else "OFF ❌"
        delay_str = f"{delay}s" if delay < 60 else f"{delay // 60}m" if delay < 3600 else f"{delay // 3600}h"
        await update.message.reply_text(
            f"🧹 Auto-delete join/leave service messages: {state}\n"
            f"⏱️ Delay: {delay_str if current else '(off hai)'}\n\n"
            "Use karo:\n"
            "/autodeletejoinleave on — turant delete\n"
            "/autodeletejoinleave on 30 — 30 second baad delete\n"
            "/autodeletejoinleave on 5m — 5 minute baad delete\n"
            "/autodeletejoinleave on 2h — 2 ghante baad delete\n"
            "/autodeletejoinleave off — band karo"
        )
        return

    enabled = context.args[0].lower() == "on"

    if not enabled:
        db.set_autodelete_joinleave(update.effective_chat.id, False)
        await update.message.reply_text("🧹 Auto-delete join/leave service messages: OFF ❌")
        return

    # Optional delay argument
    delay = 0
    if len(context.args) >= 2:
        parsed = _parse_delay(context.args[1])
        if parsed is None or parsed < 0 or parsed > 86400:
            await update.message.reply_text(
                "❌ Invalid time. Format: 30 (seconds), 5m (minutes), 2h (hours). Max 24h."
            )
            return
        delay = parsed

    db.set_autodelete_joinleave(update.effective_chat.id, True)
    db.set_autodelete_delay(update.effective_chat.id, delay)
    if delay == 0:
        await update.message.reply_text(
            "🧹 Auto-delete: ON ✅ — service messages turant delete honge."
        )
    else:
        delay_str = f"{delay}s" if delay < 60 else f"{delay // 60}m" if delay < 3600 else f"{delay // 3600}h"
        await update.message.reply_text(
            f"🧹 Auto-delete: ON ✅ — service messages {delay_str} baad delete honge."
        )


async def _delete_later(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue callback — delay ke baad service message delete."""
    data = context.job.data
    try:
        await context.bot.delete_message(data["chat_id"], data["message_id"])
    except Exception as e:
        logger.debug("Delayed delete fail %s: %s", data["chat_id"], e)


async def on_join_leave_service_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'X joined'/'X left' service messages — delay ke saath delete,
    custom leave message bhejta hai (agar /setleave se set hai)."""
    chat = update.effective_chat
    msg = update.effective_message
    if chat.type not in ("group", "supergroup") or not msg:
        return

    if msg.left_chat_member:
        leaver = msg.left_chat_member
        db.remove_seen_user(chat.id, leaver.id)

        # Custom leave message (bots skip karo)
        leave_text = db.get_leave_message(chat_id=chat.id)
        if leave_text and not leaver.is_bot:
            try:
                formatted = format_welcome_leave(leave_text, leaver, chat)
                await context.bot.send_message(chat.id, formatted, parse_mode="HTML")
            except Exception:
                try:
                    await context.bot.send_message(chat.id, formatted)
                except Exception:
                    pass

    if not db.get_autodelete_joinleave(chat.id):
        return

    delay = db.get_autodelete_delay(chat.id)
    if delay == 0:
        try:
            await msg.delete()
        except Exception:
            pass
    else:
        context.job_queue.run_once(
            _delete_later,
            delay,
            data={"chat_id": chat.id, "message_id": msg.message_id},
            name=f"joinleave_del_{chat.id}_{msg.message_id}",
        )


async def track_seen_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har normal group message pe chalta hai — /tagall ke liye active users track."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or chat.type not in ("group", "supergroup"):
        return
    db.track_user(chat.id, user.id, user.username or "", user.first_name or "")
