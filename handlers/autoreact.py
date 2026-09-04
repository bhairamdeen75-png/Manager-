"""AUTOREACT — bot har message pe automatically random reaction lagayega.
/autoreact on / off — sirf admins.

Telegram limits ka dhyan:
- Bots sirf standard emoji reactions laga sakte hain
- Flood limit se bachne ke liye har message pe react nahi karte (90% pe karte hain)
- Agar message pe already reaction hai toh skip karte hain
"""

import logging
import random

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes, CommandHandler

from handlers import store
from handlers.utils import is_admin

logger = logging.getLogger(__name__)

REACTION_POOL = [
    "👍", "❤️", "🔥", "🥰", "👏", "😁", "🤩", "🫡", "🫶", "🙏",
    "😍", "😂", "💯", "❤️‍🔥", "🤣", "🥳", "🤝", "🤗", "😎", "✨",
    "💖", "💗", "💓", "💞", "💕", "💌", "💘", "💝", "🌟", "⭐",
    "🎉", "🎊", "🚀", "🎯", "👑", "💎", "🎁", "🎈", "🏆", "🥇",
    "🤔", "🤯", "😱", "👀", "⚡", "💭", "🫠", "🥹", "💀", "😭",
    "😳", "😮", "😲", "😯", "😬", "🤐", "😐", "😑", "😶", "😶‍🌫️",
    "🙈", "🙉", "🙊", "🙋", "🤷", "🤦", "🤷‍♂️", "🤦‍♂️", "🙋‍♂️", "🔮",
    "🤬", "😢", "🥱", "🤡", "👻", "🎃", "😴", "🤮", "🤢", "😷",
    "🤒", "🤕", "😈", "👿", "👺", "👹", "☠️", "💩", "💔", "🧿",
    "✍️", "💋", "🤖", "✌️", "🤞", "🤟", "🤘", "🤙", "👈", "👉",
    "👆", "👇", "☝️", "👎", "✊", "👊", "🤛", "🤜", "🖐️", "✋",
    "🖤", "💜", "💙", "💚", "💛", "🧡", "🤍", "🤎", "🩷", "🩵",
    "🩶", "🍉", "🍿", "☕", "🍕", "🍔", "🍻", "💡", "📌", "⚠️"
]


async def cmd_autoreact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("Ye command sirf group me kaam karta hai.")
        return
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Sirf admins hi autoreact on/off kar sakte hain.")
        return

    if not context.args or context.args[0].lower() not in ("on", "off"):
        state = "ON" if store.get_autoreact(chat.id) else "OFF"
        await update.message.reply_text(
            f"🤖 Autoreact abhi: <b>{state}</b>\n"
            "Use: /autoreact on ya /autoreact off"
        )
        return

    mode = context.args[0].lower()
    store.set_autoreact(chat.id, mode == "on")
    if mode == "on":
        await update.message.reply_text(
            "🤖 <b>Autoreact ON!</b>\n"
            "Ab main har message pe random reaction lagaunga 😎\n"
            "Off karne ke liye: /autoreact off",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("😴 Autoreact OFF — ab main shant hoon.")


async def on_autoreact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """on_group_message se directly call hota hai — handler group ka issue nahi."""
    chat = update.effective_chat
    msg = update.effective_message

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False
    if not msg.from_user or msg.from_user.id == context.bot.id:
        return False
    if not msg.text and not msg.caption and not msg.photo and not msg.sticker:
        return False
    if not store.get_autoreact(chat.id):
        return False
    if random.random() < 0.01:  # flood se bachne ke liye 10% skip
        return False
    if msg.reactions and any(
        getattr(r.user, "id", None) == context.bot.id for r in msg.reactions
    ):
        return False

    emoji = random.choice(REACTION_POOL)
    try:
        await msg.set_reaction(emoji)
    except Exception as e:
        logger.info("Autoreact skip (%s): %s", chat.id, e)
        return False
    return False
