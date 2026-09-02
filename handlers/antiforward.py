"""Anti-Forward — jab ON ho, sirf admins forwarded messages bhej sakte hain.
Users ka forward delete + warn message. /antiforward on|off se toggle."""

import logging

from telegram import Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes, MessageHandler, filters

import database as db
from handlers import store
from handlers.utils import is_admin

logger = logging.getLogger(__name__)


async def cmd_antiforward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args or context.args[0].lower() not in ("on", "off"):
        current = db.get_antiforward(update.effective_chat.id)
        state = "ON ✅ (forwarding band hai)" if current else "OFF ❌ (forwarding free hai)"
        await update.message.reply_text(
            f"🚫 Anti-Forward abhi: {state}\n"
            f"Badalne ke liye: /antiforward on|off\n\n"
            f"<i>ON hone pe sirf admins forwarded messages bhej sakte hain — "
            f"users ke forward delete ho jayenge.</i>",
            parse_mode="HTML",
        )
        return
    enabled = context.args[0].lower() == "on"
    db.set_antiforward(update.effective_chat.id, enabled)
    state = "ON ✅ — ab sirf admins forward kar sakte hain" if enabled else "OFF ❌"
    await update.message.reply_text(f"🚫 Anti-Forward: {state}")


async def check_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Passive pipeline se call hota hai. True = forward delete hua."""
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or user.is_bot:
        return False
    if not db.get_antiforward(chat.id):
        return False
    # Forwarded message check — forward_origin hota hai forwarded messages pe
    if not msg.forward_origin:
        return False
    if await is_admin(update, context) or store.is_approved(chat.id, user.id):
        return False
    try:
        await msg.delete()
        await chat.send_message(
            f"🚫 {user.mention_html()} — is group me forwarding band hai! "
            f"Sirf admins forward kar sakte hain.",
            parse_mode="HTML",
        )
    except (BadRequest, Forbidden) as e:
        logger.warning("Anti-forward delete fail %s: %s", chat.id, e)
    return True
