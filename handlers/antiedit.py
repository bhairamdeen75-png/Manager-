"""Edited messages ko bhi spam check — log spam karke message delete."""

import logging

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

import database as db
from handlers import store
from handlers.spamscore import spam_score
from handlers.utils import is_admin

logger = logging.getLogger(__name__)


async def on_edited(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.edited_message
    if not msg:
        return
    user = msg.from_user
    chat = update.effective_chat
    if not user or user.is_bot:
        return
    if await is_admin(update, context) or store.is_approved(chat.id, user.id):
        return
    text = msg.text or msg.caption or ""
    if spam_score(text) >= store.get_spam_threshold(chat.id):
        try:
            await msg.delete()
            await chat.send_message(
                f"✏️ {user.mention_html()} ne edit karke spam bheja — delete kar diya.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Antiedit fail %s: %s", chat.id, e)
