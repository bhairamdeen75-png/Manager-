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
    if await is_admin(update, context) or await store.is_approved(chat.id, user.id):
        return
    text = msg.text or msg.caption or ""
    if spam_score(text) >= await store.get_spam_threshold(chat.id):
        try:
            await msg.delete()
            await chat.send_message(
                 f"🛡️ <b>EDIT-SPAM BLOCKED</b>\n"
                 f"━━━━━━━━━━━━━━━━━━━━━\n"
                 f"👤 <b>User:</b> {user.mention_html()}\n"
                 f"🔍 <b>Reason:</b> Message edit karke stealth spam 🥷\n"
                 f"🗑️ <b>Action:</b> Message instant delete kar diya!\n"
                 f"━━━━━━━━━━━━━━━━━━━━━\n"
                 f"<i>Nice try, par Manager ki nazar se bachna namumkin hai! 😉</i>",
             parse_mode="HTML",
           )

        except Exception as e:
            logger.warning("Antiedit fail %s: %s", chat.id, e)
