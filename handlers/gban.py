"""Owner-level scammer database — ek baar /gban, saare groups me ban.

Enforcement: har group message pe check — gbanned user ka message aaye toh
message delete + group se ban. Owner Panel ke broadcast pattern jaisa loop.
"""

import logging

from telegram import Update
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes, MessageHandler, filters

import database as db
from handlers import store
from config import OWNER_IDS

logger = logging.getLogger(__name__)


def _is_owner(user_id):
    return user_id in OWNER_IDS


async def cmd_gban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update.effective_user.id):
        await update.message.reply_text("Ye command sirf bot owner ke liye hai.")
        return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("Format: /gban <user_id> [reason]")
        return
    uid = int(context.args[0])
    reason = " ".join(context.args[1:]) or "Scammer"
    store.gban_add(uid, reason, update.effective_user.id)
    await update.message.reply_text(
        f"⛔ {uid} globally ban ho gaya. Reason: {reason}\n"
        f"Saare groups me enforce hoga jab wo message karega."
    )


async def cmd_ungban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update.effective_user.id):
        return
    if not context.args or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("Format: /ungban <user_id>")
        return
    store.gban_remove(int(context.args[0]))
    await update.message.reply_text("✅ Global ban hata diya.")


async def cmd_gbans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update.effective_user.id):
        return
    bans = store.gban_list()
    if not bans:
        await update.message.reply_text("Global ban list khali hai.")
        return
    lines = ["⛔ **Global bans:**"] + [
        f"• `{b['user_id']}` — {b.get('reason', '?')}" for b in bans
    ]
    await update.message.reply_text("\n".join(lines))


async def on_gban_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passive: gbanned user ka message delete + group se ban."""
    user = update.effective_user
    chat = update.effective_chat
    if not user or store.is_gbanned(user.id) is None:
        return
    try:
        await update.effective_message.delete()
        await context.bot.ban_chat_member(chat.id, user.id)
    except (BadRequest, Forbidden) as e:
        logger.warning("Gban enforce fail %s: %s", chat.id, e)
