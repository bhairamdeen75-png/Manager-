"""Welcome media + buttons — naye member ko photo/GIF/video + custom buttons welcome.

/setwmedia — kisi photo/GIF/video pe reply karke (caption optional)
/setwbtn <Text | URL> — buttons (multiple lines = multiple buttons)
/clearwmedia / /clearwbtn — hatao
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters

import database as db
from handlers import store
from handlers.utils import is_admin

logger = logging.getLogger(__name__)


def build_kb(buttons):
    rows = []
    for b in buttons:
        if b.get("text") and b.get("url", "").startswith("http"):
            rows.append([InlineKeyboardButton(b["text"], url=b["url"])])
    return InlineKeyboardMarkup(rows) if rows else None


async def cmd_setwmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    msg = update.effective_message
    r = msg.reply_to_message
    if not r:
        await msg.reply_text("Kisi photo/GIF/video pe reply karke /setwmedia bhejo.")
        return
    if r.photo:
        store.set_welcome_media(update.effective_chat.id, r.photo[-1].file_id, "photo")
    elif r.animation:
        store.set_welcome_media(update.effective_chat.id, r.animation.file_id, "animation")
    elif r.video:
        store.set_welcome_media(update.effective_chat.id, r.video.file_id, "video")
    else:
        await msg.reply_text("Sirf photo, GIF ya video chalega.")
        return
    await msg.reply_text("✅ Welcome media set ho gaya!")


async def cmd_setwbtn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    text = " ".join(context.args) if context.args else ""
    if "|" not in text:
        await update.message.reply_text("Format: /setwbtn Rules | https://example.com")
        return
    buttons = []
    for line in text.splitlines():
        if "|" in line:
            t, u = line.split("|", 1)
            t, u = t.strip(), u.strip()
            if t and u.startswith("http"):
                buttons.append({"text": t, "url": u})
    if not buttons:
        await update.message.reply_text("Koi valid button nahi bana (URL http se shuru hona chahiye).")
        return
    store.set_welcome_buttons(update.effective_chat.id, buttons)
    await update.message.reply_text(f"✅ {len(buttons)} welcome buttons set!")


async def cmd_clearwmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context):
        store.clear_welcome_media(update.effective_chat.id)
        await update.message.reply_text("🧹 Welcome media hata diya.")


async def cmd_clearwbtn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await is_admin(update, context):
        store.clear_welcome_buttons(update.effective_chat.id)
        await update.message.reply_text("🧹 Welcome buttons hata diye.")


async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Naye member ko media welcome — captcha se independent (turant bhejta hai)."""
    chat = update.effective_chat
    media = store.get_welcome_media(chat.id)
    buttons = store.get_welcome_buttons(chat.id)
    if not media and not buttons:
        return
    kb = build_kb(buttons)
    for new in update.message.new_chat_members:
        if new.is_bot:
            continue
        text = f"👋 Welcome {new.mention_html()}!"
        try:
            if media and media["type"] == "photo":
                await context.bot.send_photo(chat.id, media["file_id"], caption=text,
                                             parse_mode="HTML", reply_markup=kb)
            elif media and media["type"] == "animation":
                await context.bot.send_animation(chat.id, media["file_id"], caption=text,
                                                 parse_mode="HTML", reply_markup=kb)
            elif media and media["type"] == "video":
                await context.bot.send_video(chat.id, media["file_id"], caption=text,
                                             parse_mode="HTML", reply_markup=kb)
            elif kb:
                await context.bot.send_message(chat.id, text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            logger.warning("Welcome media fail %s: %s", chat.id, e)
