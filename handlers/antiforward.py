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
        current = await db.get_antiforward(update.effective_chat.id)
        state = "ON ✅ (forwarding band hai)" if current else "OFF ❌ (forwarding free hai)"
        await update.message.reply_text(
             f"🛡️ <b>ANTI-FORWARD CONTROL PANEL</b>\n"
             f"━━━━━━━━━━━━━━━━━━━━━\n"
             f"⚙️ <b>Current Status:</b> <b>{state}</b>\n\n"
             f"📌 <b>Commands:</b>\n"
             f"├ <code>/antiforward on</code>  — Enable anti-forward\n"
             f"└ <code>/antiforward off</code> — Disable anti-forward\n"
             f"━━━━━━━━━━━━━━━━━━━━━\n"
             f"ℹ️ <i>ON hone par normal users ke forwarded messages auto-delete ho jayenge. Sirf Admins forward kar sakte hain! 👑</i>",
             parse_mode="HTML",
       )

        return
    enabled = context.args[0].lower() == "on"
    await db.set_antiforward(update.effective_chat.id, enabled)
    state = "ON ✅ — ab sirf admins forward kar sakte hain" if enabled else "OFF ❌"
    await update.message.reply_text(f"🚫 Anti-Forward: {state}")


async def check_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Passive pipeline se call hota hai. True = forward delete hua."""
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or user.is_bot:
        return False
    if not await db.get_antiforward(chat.id):
        return False
    # Forwarded message check — forward_origin hota hai forwarded messages pe
    if not msg.forward_origin:
        return False
    if await is_admin(update, context) or await store.is_approved(chat.id, user.id):
        return False
    try:
        await msg.delete()
        await chat.send_message(
             f"🚫 <b>FORWARD NOT ALLOWED!</b>\n"
             f"━━━━━━━━━━━━━━━━━━━━━\n"
             f"👤 <b>User:</b> {user.mention_html()}\n"
             f"⚠️ <b>Reason:</b> Forwarded message detect hua\n"
             f"🗑️ <b>Action:</b> Message delete kar diya gaya\n"
             f"━━━━━━━━━━━━━━━━━━━━━\n"
             f"<i>Apna original content likho dost, forward karna allowed nahi hai! 😉</i>",
             parse_mode="HTML",
      )

    except (BadRequest, Forbidden) as e:
        logger.warning("Anti-forward delete fail %s: %s", chat.id, e)
    return True
