import random

from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

import database as db
from config import CAPTCHA_TIMEOUT_SECONDS

# pending[(chat_id, user_id)] = {"answer": int, "message_id": int}
_pending: dict[tuple[int, int], dict] = {}


async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return

    for member in update.effective_message.new_chat_members:
        if member.is_bot:
            continue

        key = (chat.id, member.id)

        # Restrict user until they solve the captcha
        try:
            await context.bot.restrict_chat_member(
                chat.id,
                member.id,
                permissions=ChatPermissions(can_send_messages=False),
            )
        except Exception:
            pass

        a, b = random.randint(1, 9), random.randint(1, 9)
        correct = a + b
        options = {correct}
        while len(options) < 4:
            options.add(random.randint(2, 18))
        options = list(options)
        random.shuffle(options)

        buttons = [
            InlineKeyboardButton(
                str(opt), callback_data=f"captcha:{chat.id}:{member.id}:{opt}"
            )
            for opt in options
        ]
        keyboard = InlineKeyboardMarkup([buttons])

        sent = await context.bot.send_message(
            chat.id,
            f"👋 {member.mention_html()}, group me welcome!\n\n"
            f"Bot ke saath verify karo: <b>{a} + {b} = ?</b>\n"
            f"({CAPTCHA_TIMEOUT_SECONDS} second me solve karo, warna kick ho jaoge)",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        _pending[key] = {"answer": correct, "message_id": sent.message_id}

        context.job_queue.run_once(
            _captcha_timeout,
            CAPTCHA_TIMEOUT_SECONDS,
            data={"chat_id": chat.id, "user_id": member.id, "message_id": sent.message_id},
            name=f"captcha_timeout_{chat.id}_{member.id}",
        )


async def _captcha_timeout(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    chat_id, user_id, message_id = job_data["chat_id"], job_data["user_id"], job_data["message_id"]
    key = (chat_id, user_id)

    if key not in _pending:
        return  # already solved

    del _pending[key]
    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        await context.bot.unban_chat_member(chat_id, user_id)  # kick, not permanent ban
    except Exception:
        pass
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="⏰ Captcha timeout — user ko kick kar diya gaya.",
        )
    except Exception:
        pass


async def on_captcha_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, chat_id, user_id, answer = query.data.split(":")
    chat_id, user_id, answer = int(chat_id), int(user_id), int(answer)
    key = (chat_id, user_id)

    if query.from_user.id != user_id:
        await query.answer("Ye captcha tumhare liye nahi hai.", show_alert=True)
        return

    if key not in _pending:
        await query.answer("Captcha expire ho chuka hai.", show_alert=True)
        return

    correct = _pending[key]["answer"]
    if answer == correct:
        del _pending[key]
        try:
            await context.bot.restrict_chat_member(
                chat_id,
                user_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_audios=True,
                    can_send_documents=True,
                    can_send_photos=True,
                    can_send_videos=True,
                    can_send_video_notes=True,
                    can_send_voice_notes=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                ),
            )
        except Exception:
            pass

        welcome_text = db.get_welcome(chat_id) or "🎉 Verify ho gaya! Group rules follow karo aur enjoy karo."
        await query.edit_message_text(f"✅ Verification successful!\n\n{welcome_text}")
        await query.answer("Verified!")
    else:
        await query.answer("❌ Galat jawab, dobara try karo.", show_alert=True)
