import time
from datetime import datetime, timedelta, timezone

from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes

import database as db
from config import FLOOD_MSG_LIMIT, FLOOD_TIME_WINDOW, FLOOD_MUTE_MINUTES, MAX_WARNS
from handlers.utils import is_admin

_message_log: dict[tuple[int, int], list[float]] = {}


async def check_flood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat

    if not msg or not user or chat.type not in ("group", "supergroup"):
        return

    # Pehle apna alag get_chat_member call tha — ab cached is_admin() use karo
    if await is_admin(update, context):
        return

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
                f"🛡️ <b>ANTI-FLOOD PROTECTION</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>User:</b> {user.mention_html()}\n"
                f"⚠️ <b>Violation:</b> Rapid message spam detected\n"
                f"🔇 <b>Action:</b> Muted for {FLOOD_MUTE_MINUTES} minutes\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"<i>Slow down! Group rules apply to everyone. ⏱️</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass

        count = await db.add_warn(chat.id, user.id)
        if count >= MAX_WARNS:
            await db.reset_warns(chat.id, user.id)
            try:
                await context.bot.ban_chat_member(chat.id, user.id)
                await msg.reply_text(
                    f"⛔ <b>USER BANNED — SPAM LIMIT REACHED</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>User:</b> {user.mention_html()}\n"
                    f"🚫 <b>Reason:</b> Repeated spam violations (Max warnings exceeded)\n"
                    f"🔨 <b>Action:</b> Permanently banned from the group\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Group discipline is our top priority. 🚫</i>",
                    parse_mode="HTML",
                )
            except Exception:
                pass

