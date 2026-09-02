"""Captcha types — math (default), button (4 inline buttons), image (Pillow distorted text).

/setcaptchamode math|button|image se toggle.
Button mode bots ke liye sabse tough hai — sahi button tap karna padta hai.
Image mode Pillow se distorted text image generate hoti hai (100% offline, free).
"""

import logging
import random
import io
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

import database as db
from handlers import store
from handlers.captcha import (
    mute_user_for_captcha,
    unmute_and_welcome,
    CAPTCHA_MUTE_MINUTES,
)

logger = logging.getLogger(__name__)

CAPTCHA_WORDS = ["secr3t", "cod3x", "plug1n", "vibot", "m4nagr", "t3legr", "s3cur3", "b0tprs"]


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
    # Distorted text — har char pe random offset + rotation-ish jitter
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


async def send_button_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE,
                              chat_id: int, user_id: int, user_name: str):
    """4 buttons — 1 sahi, 3 galat. Galat tap = retry, 3 fail = auto-kick."""
    correct = random.randint(0, 3)
    buttons = []
    for i in range(4):
        label = "✅ Click karo" if i == correct else "❌ Galat"
        buttons.append([InlineKeyboardButton(label, callback_data=f"captchaplus:{i}:{user_id}:{correct}")])
    await context.bot.send_message(
        chat_id,
        f"🔐 {user_name} — captcha solve karo! Neeche **sahi button** tap karo "
        f"({CAPTCHA_MUTE_MINUTES} min me timeout = kick).",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )

async def send_image_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE,
                             chat_id: int, user_id: int, user_name: str):
    """Image captcha — distorted text, user ko type karke bhejna hota hai."""
    word = random.choice(CAPTCHA_WORDS)
    img_bytes = gen_captcha_image(word)
    await context.bot.send_photo(
        chat_id,
        photo=img_bytes,
        caption=f"🔐 {user_name} — image me likha text type karo "
                f"({CAPTCHA_MUTE_MINUTES} min timeout = kick).",
        parse_mode="HTML",
    )
    # Expected answer store karo — user ke agle message me match hoga
    context.chat_data[f"imgcaptcha_{user_id}"] = word


async def on_captcha_plus_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Button captcha callback — pattern r'^captchaplus:' se register hota hai."""
    query = update.callback_query
    data = query.data.split(":")
    _, tapped, user_id, correct = data
    if int(user_id) != query.from_user.id:
        await query.answer("Ye captcha tumhara nahi hai!", show_alert=True)
        return
    if tapped == correct:
        await query.answer("✅ Captcha solve ho gaya!")
        await unmute_and_welcome(update, context, query.message.chat_id, int(user_id))
        try:
            await query.message.delete()
        except Exception:
            pass
    else:
        await query.answer("❌ Galat button! Dobara try karo.", show_alert=True)


async def on_image_captcha_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Image captcha text answer — passive pipeline se call hota hai."""
    user = update.effective_user
    chat = update.effective_chat
    if not user:
        return
    key = f"imgcaptcha_{user.id}"
    if key not in (context.chat_data or {}):
        return
    expected = context.chat_data[key]
    if (update.effective_message.text or "").strip().lower() == expected.lower():
        context.chat_data.pop(key, None)
        await unmute_and_welcome(update, context, chat.id, user.id)
        await update.effective_message.reply_text(f"✅ Captcha solve! Welcome {user.first_name}!")
    else:
        await update.effective_message.reply_text("❌ Galat text! Dobara type karo.")
