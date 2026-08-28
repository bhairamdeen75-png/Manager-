from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin


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
    await update.message.reply_text(f"🧹 Auto-delete join/leave messages: {state}")


async def on_join_leave_service_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Deletes 'X joined' / 'X left' service messages if the setting is enabled.
    Also cleans up the seen_users list when someone leaves."""
    chat = update.effective_chat
    msg = update.effective_message
    if chat.type not in ("group", "supergroup") or not msg:
        return

    if msg.left_chat_member:
        db.remove_seen_user(chat.id, msg.left_chat_member.id)

    if not db.get_autodelete_joinleave(chat.id):
        return

    try:
        await msg.delete()
    except Exception:
        pass


async def track_seen_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Runs on every normal group text message so we know who is active in the
    group (needed for /tagall, since bots can't list all members directly)."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat or chat.type not in ("group", "supergroup"):
        return
    db.track_user(chat.id, user.id, user.username or "", user.first_name or "")
