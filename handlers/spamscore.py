"""Heuristic spam score — caps, emoji spam, repeated chars, punctuation. Free, no API."""

import logging
import re
from datetime import datetime, timedelta, timezone

from telegram import Update, ChatPermissions
from telegram.error import Forbidden
from telegram.ext import ContextTypes

import database as db
from config import BOT_CREDIT
from handlers import store, panel
from handlers.utils import is_admin

logger = logging.getLogger(__name__)

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U0001F000-\U0001F02F\uFE0F]"
)
REPEAT_RE = re.compile(r"(.)\1{4,}")  # aaaaa


def spam_score(text: str) -> int:
    score = 0
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 10 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        score += 3
    if len(EMOJI_RE.findall(text)) > 5:
        score += 2
    if REPEAT_RE.search(text):
        score += 2
    if len(re.findall(r"[!?]{3,}", text)) > 0:
        score += 1
    words = text.split()
    if words and len(set(w.lower() for w in words)) == 1 and len(words) >= 5:
        score += 2  # same word repeat spam
    return score


async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Passive pipeline se call hota hai. True = action liya (message delete + mute)."""
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or user.is_bot:
        return False
    if await is_admin(update, context) or store.is_approved(chat.id, user.id):
        return False

    score = spam_score(msg.text or "")
    threshold = store.get_spam_threshold(chat.id)
    if score < threshold:
        return False

    try:
        await msg.delete()
        await context.bot.restrict_chat_member(
            chat.id, user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        await chat.send_message(
            f"🧠 Spam score {score}/{threshold} — {user.mention_html()} 30 min ke liye mute. "
            f"Message delete kar diya. ({BOT_CREDIT})",
            parse_mode="HTML",
        )
    except Forbidden:
        # Bot ko restrict/delete ki permission nahi — sirf log karo, crash na ho
        logger.warning(
            "Spam score hit but bot lacks delete/restrict permission in %s", chat.id
        )
    return True
