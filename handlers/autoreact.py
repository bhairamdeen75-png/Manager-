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

# Reaction emoji pool — sab Telegram standard reactions hain
REACTION_POOL = [
    # Positivity, Love & Celebration
    "👍", "❤️", "🔥", "🥰", "👏", "😁", "🤩", "🫡", "🫶", "🙏",
    "😍", "😂", "💯", "❤️‍🔥", "🤣", "🥳", "🤝", "🤗", "😎", "✨",
    "💖", "💗", "💓", "💞", "💕", "💌", "💘", "💝", "🌟", "⭐",
    "🎉", "🎊", "🚀", "🎯", "👑", "💎", "🎁", "🎈", "🏆", "🥇",

    # Expressions, Surprises & Reactions
    "🤔", "🤯", "😱", "👀", "⚡", "💭", "🫠", "🥹", "💀", "😭",
    "😳", "😮", "😲", "😯", "😬", "🤐", "😐", "😑", "😶", "😶‍🌫️",
    "🙈", "🙉", "🙊", "🙋", "🤷", "🤦", "🤷‍♂️", "🤦‍♂️", "🙋‍♂️", "🔮",

    # Playful, Dark & Negative
    "🤬", "😢", "🥱", "🤡", "👻", "🎃", "😴", "🤮", "🤢", "😷",
    "🤒", "🤕", "😈", "👿", "👺", "👹", "☠️", "💩", "💔", "🧿",

    # Gestures & Hands
    "✍️", "💋", "🤖", "✌️", "🤞", "🤟", "🤘", "🤙", "👈", "👉",
    "👆", "👇", "☝️", "👎", "✊", "👊", "🤛", "🤜", "🖐️", "✋",

    # Hearts & Miscellaneous
    "🖤", "💜", "💙", "💚", "💛", "🧡", "🤍", "🤎", "🩷", "🩵",
    "🩶", "🍉", "🍿", "☕", "🍕", "🍔", "🍻", "💡", "📌", "⚠️"
]


# Emoji + message combo — kabhi kabhi reaction ke saath mazakiya comment bhi
FUNNY_COMMENTS = [
    "Ye message toh react bhi deserve karta hai 😎",
    "Reaction de diya, ab khush? 😂",
    "Bot bhi fan ho gaya is message ka 🔥",
    "Random reaction aa gaya — kal ki baat kal dekhenge 🎲",
    "Isko toh award milna chahiye 🏆",
    "React kar diya bhai, aur kya chahiye 😄",
]


async def cmd_autoreact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Turn autoreact on/off — admin only."""
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
    """
    on_group_message pipeline se call hota hai.
    True = message consume hua (autoreact ke baad aage kuch nahi karna).
    """
    chat = update.effective_chat
    msg = update.effective_message

    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False

    # Bot ke apne messages pe react nahi karte (infinite loop se bachne ke liye)
    if not msg.from_user or msg.from_user.id == context.bot.id:
        return False

    # Service messages (join/leave) pe react nahi karte
    if not msg.text and not msg.caption and not msg.photo and not msg.sticker:
        return False

    if not store.get_autoreact(chat.id):
        return False

    # Flood limit se bachne ke liye — 10 me se 1 message skip karte hain
    if random.random() < 0.10:
        return False

    # Agar message pe bot ka already reaction hai toh skip
    if msg.reactions and any(
        getattr(r.user, "id", None) == context.bot.id for r in msg.reactions
    ):
        return False

    emoji = random.choice(REACTION_POOL)
    try:
        await msg.set_reaction(emoji)
    except Exception as e:
        # "Reaction_invalid" ya flood limit — chupchap skip karo, error spam nahi
        logger.debug(f"Autoreact skip ({chat.id}): {e}")
        return False

    # 2% chance — reaction ke saath mazakiya comment bhi
    if random.random() < 0.02:
        try:
            await msg.reply_text(random.choice(FUNNY_COMMENTS))
        except Exception:
            pass

    return False  # False return karte hain — pipeline aage chalta rahega
    # (react karna message consume nahi karta — notes, spam checks sab chalte rahenge)


def register(app):
    app.add_handler(CommandHandler("autoreact", cmd_autoreact), group=5)
