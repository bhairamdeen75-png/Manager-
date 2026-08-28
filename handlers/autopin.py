from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin


async def cmd_autopin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Use karo: /autopin on|off\n(ON hone par admins ke messages auto-pin ho jayenge)")
        return
    enabled = context.args[0].lower() == "on"
    db.set_autopin(update.effective_chat.id, enabled)
    state = "ON ✅" if enabled else "OFF ❌"
    await update.message.reply_text(f"📌 Auto-pin admin messages: {state}")


async def maybe_autopin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Runs on every group text message — silently pins messages sent by admins if enabled."""
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not user or chat.type not in ("group", "supergroup"):
        return
    if not db.get_autopin(chat.id):
        return
    if not await is_admin(update, context, user.id):
        return
    try:
        await context.bot.pin_chat_message(chat.id, msg.message_id, disable_notification=True)
    except Exception:
        pass
