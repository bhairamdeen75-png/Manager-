"""Captcha types — math (default, captcha.py me), button (4 inline buttons), image (Pillow).

/setcaptchamode math|button|image se toggle.
Button/image modes captchaplus ke apne hain — captcha.py se koi import nahi.
"""

import io
import logging
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

import database as db
from handlers import store
from config import CAPTCHA_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

CAPTCHA_WORDS = ["secr3t", "cod3x", "plug1n", "vibot", "m4nagr", "t3legr", "s3cur3", "b0tprs"]

FULL_PERMS = ChatPermissions(
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
)


async def cmd_setcaptchamode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin ke liye — /setcaptchamode math|button|image"""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Ye command group me use karo.")
        return
    if not (await chat.get_member(update.effective_user.id)).status in ("administrator", "creator"):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args or context.args[0] not in ("math", "button", "image"):
        current = store.get_captcha_mode(chat.id)
        await update.message.reply_text(
            f"Abhi mode hai: <b>{current}</b>\n"
            f"Badalne ke liye: /setcaptchamode math|button|image",
            parse_mode="HTML",
        )
        return
    mode = context.args[0]
    store.set_captcha_mode(chat.id, mode)
    await update.message.reply_text(f"✅ Captcha mode set: <b>{mode}</b>", parse_mode="HTML")


def gen_captcha_image(text: str) -> bytes:
    """Pillow se distorted captcha image — offline, no API."""
    img = Image.new("RGB", (280, 90), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    # Background noise lines
    for _ in range(6):
        x1, y1 = random.randint(0, 280), random.randint(0, 90)
        x2, y2 = random.randint(0, 280), random.randint(0, 90)
        draw.line((x1, y1, x2, y2), fill=(random.randint(100, 200),) * 3, width=2)
    # Distorted text — har char pe random offset
    x = 20
    for ch in text:
        y = 20 + random.randint(-8, 8)
        color = (random.randint(0, 100), random.randint(0, 100), random.randint(0, 100))
        draw.text((x, y), ch, fill=color, font=font)
        x += 30 + random.randint(-4, 4)
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _restrict_and_send_captcha(context: ContextTypes.DEFAULT_TYPE, chat_id: int,
                                     user_id: int, user_name: str):
    """Naye member ko mute karo aur mode ke hisaab se captcha bhejo."""
    mode = store.get_captcha_mode(chat_id)

    # Pehle mute (captcha solve tak)
    try:
        await context.bot.restrict_chat_member(
            chat_id, user_id, permissions=ChatPermissions(can_send_messages=False)
        )
    except Exception:
        logger.warning("Captcha mute fail %s (bot ko Ban users permission chahiye)", chat_id)

    if mode == "button":
        correct = random.randint(0, 3)
        buttons = [
            [InlineKeyboardButton(
                f"🔑 Option {i + 1}",
                callback_data=f"captchaplus:{i}:{user_id}:{correct}",
            )]
            for i in range(4)
        ]
        random.shuffle(buttons)
        await context.bot.send_message(
            chat_id,
            f"👋 {user_name}, verify karo!\n\n"
            f"Neeche wale 4 buttons me se <b>koi bhi ek tap karo</b> — galat hua toh dobara try kar sakte ho.\n"
            f"({CAPTCHA_TIMEOUT_SECONDS} second me solve karo, warna kick ho jaoge)",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    elif mode == "image":
        word = random.choice(CAPTCHA_WORDS)
        img_bytes = gen_captcha_image(word)
        await context.bot.send_photo(
            chat_id,
            photo=img_bytes,
            caption=f"👋 {user_name}, verify karo!\n\n"
                    f"Image me jo text likha hai wo type karo.\n"
                    f"({CAPTCHA_TIMEOUT_SECONDS} second me solve karo, warna kick ho jaoge)",
        )
        # Expected answer — user ke agle message me match hoga
        context.chat_data[f"imgcaptcha_{user_id}"] = word
    else:
        # math mode — original captcha.py ka flow chalao
        return False
    return True


async def _unmute_and_welcome(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    """Captcha solve hone pe permissions wapas + welcome message."""
    try:
        await context.bot.restrict_chat_member(chat_id, user_id, permissions=FULL_PERMS)
    except Exception:
        logger.warning("Unmute fail %s user %s", chat_id, user_id)
    welcome_text = db.get_welcome(chat_id) or "🎉 Verify ho gaya! Group rules follow karo aur enjoy karo."
    return welcome_text


async def on_captcha_plus_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Button captcha callback — pattern r'^captchaplus:'."""
    query = update.callback_query
    _, tapped, user_id, correct = query.data.split(":")
    user_id, correct = int(user_id), int(correct)

    if query.from_user.id != user_id:
        await query.answer("Ye captcha tumhare liye nahi hai.", show_alert=True)
        return

    if int(tapped) == correct:
        welcome_text = await _unmute_and_welcome(context, query.message.chat_id, user_id)
        try:
            await query.edit_message_text(
                f"✅ Verification successful!\n\n{welcome_text}"
            )
        except Exception:
            pass
        await query.answer("Verified!")
    else:
        await query.answer("❌ Galat button! Dobara try karo.", show_alert=True)


async def on_image_captcha_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Image captcha text answer — passive pipeline se call hota hai.
    True = message consume hua (captcha ke related tha), False = normal message."""
    user = update.effective_user
    chat = update.effective_chat
    msg = update.effective_message
    if not user or not msg or not msg.text:
        return False
    key = f"imgcaptcha_{user.id}"
    if key not in context.chat_data:
        return False

    expected = context.chat_data[key]
    if msg.text.strip().lower() == expected.lower():
        context.chat_data.pop(key, None)
        welcome_text = await _unmute_and_welcome(context, chat.id, user.id)
        try:
            await msg.reply_text(f"✅ Verification successful!\n\n{welcome_text}")
        except Exception:
            pass
        return True

    await msg.reply_text("❌ Galat text! Dobara type karo.")
    return True
