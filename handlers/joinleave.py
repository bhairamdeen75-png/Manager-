from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin, format_welcome_leave


async def cmd_autodeletejoinleave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Use karo: /autodeletejoinleave on|off")
        return
    enabled = context.args[0].lower() == "on"
    db.set_autodelete_joinleave(update.effective_chat.id, enabled)
    state = "ON ✅" if enabled else "OFF ❌"
    await update.message.reply_text(f"🧹 Auto-delete join/leave service messages: {state}")


async def on_join_leave_service_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'X joined'/'X left' service messages delete karta hai (agar setting on hai),
    custom leave message bhejta hai (agar /setleave se set hai), aur
    seen_users list clean karta hai."""
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
                pass

    if not db.get_autodelete_joinleave(chat.id):
        return

    try:
        await msg.delete()
    except Exception:
        pass


async def track_seen_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har normal group message pe chalta hai — /tagall ke liye active users track."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or chat.type not in ("group", "supergroup"):
        return
    db.track_user(chat.id, user.id, user.username or "", user.first_name or "")
