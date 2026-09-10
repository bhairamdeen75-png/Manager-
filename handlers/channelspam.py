"""Anti-Channel-Spam — jab koi user apna channel group me attach karke auto-forward
posts bhejta hai (sender_chat = linked channel), toh message delete + sender mute.

Register in bot.py:
    from handlers import channelspam
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND,
        channelspam.on_group_message
    ), group=2)
"""

import logging
from datetime import datetime, timedelta, timezone

from telegram import Update, ChatPermissions
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin

logger = logging.getLogger(__name__)

MUTE_MINUTES = 60


async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har group message pe chalta hai. Auto-forwarded channel post detect karta hai."""
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    # Naya pipeline: PTB v20+ me is_automatic_forward bool hota hai
    # (jab user apna channel group se attach karta hai aur post auto-forward hoti hai)
    if not msg or not getattr(msg, "is_automatic_forward", False):
        return

    # Anonymous admins / channel posts ke liye from_user None ho sakta hai
    if not user or user.is_bot:
        return

    # Admins aur approved (trusted) users exempt
    if await is_admin(update, context) or db.is_approved(chat.id, user.id):
        return

    try:
        await msg.delete()
    except (BadRequest, Forbidden) as e:
        logger.warning("Channel-spam message delete nahi hua %s: %s", chat.id, e)

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            ),
            until_date=datetime.now(timezone.utc) + timedelta(minutes=MUTE_MINUTES),
        )
        await chat.send_message(
            f"📺 {user.mention_html()} ne channel auto-forward kiya — "
            f"message delete + {MUTE_MINUTES} min mute.",
            parse_mode="HTML",
        )
    except (BadRequest, Forbidden) as e:
        # Bot ko ban/restrict permission nahi — kam se kam try delete toh ho gaya
        logger.warning("Channel-spam mute fail %s: %s", chat.id, e)
