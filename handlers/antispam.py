import time
from datetime import datetime, timedelta, timezone

from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes

import database as db
from config import FLOOD_MSG_LIMIT, FLOOD_TIME_WINDOW, FLOOD_MUTE_MINUTES, MAX_WARNS

# In-memory flood tracker: {(chat_id, user_id): [timestamps]}
_message_log: dict[tuple[int, int], list[float]] = {}


async def check_flood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Run on every group text message. Mutes users who send too many messages too fast."""
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not msg or not user or chat.type not in ("group", "supergroup"):
        return

    # Don't flood-check admins
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in ("administrator", "creator"):
            return
    except Exception:
        pass

    key = (chat.id, user.id)
    now = time.time()
    timestamps = _message_log.setdefault(key, [])
    timestamps.append(now)

    # keep only messages inside the time window
    cutoff = now - FLOOD_TIME_WINDOW
    _message_log[key] = [t for t in timestamps if t >= cutoff]

    if len(_message_log[key]) >= FLOOD_MSG_LIMIT:
        _message_log[key] = []  # reset so we don't re-trigger every message
        until = datetime.now(timezone.utc) + timedelta(minutes=FLOOD_MUTE_MINUTES)
        try:
            await context.bot.restrict_chat_member(
                chat.id,
                user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
            await msg.reply_text(
                f"🚫 {user.mention_html()} spam kar raha tha, {FLOOD_MUTE_MINUTES} minute ke liye mute.",
                parse_mode="HTML",
            )
        except Exception:
            pass

        count = db.add_warn(chat.id, user.id)
        if count >= MAX_WARNS:
            db.reset_warns(chat.id, user.id)
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
                await msg.reply_text(f"⛔ {user.mention_html()} ban kar diya gaya (baar baar spam).", parse_mode="HTML")
            except Exception:
                pass
