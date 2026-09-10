"""AUTOREACT — bot ab message ka mood samajh kar reaction lagayega
(random ulta-sidha nahi — funny message pe hasi wala emoji, sad pe sad wala, etc).
/autoreact on / off — sirf admins.

Telegram limits ka dhyan:
- Bots sirf standard emoji reactions laga sakte hain
- Flood limit se bachne ke liye har message pe react nahi karte (~99% pe karte hain)
- Agar koi mood match nahi hota toh ek safe general pool se pick karte hain
"""

import logging
import random
import re

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes, CommandHandler

from handlers import store
from handlers.utils import is_admin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mood -> keywords (English + Hindi/Hinglish, sab lowercase substring match)
# Order yahi priority order bhi hai jab multiple moods match ho jaayein.
# ---------------------------------------------------------------------------
MOOD_KEYWORDS = {
    "funny": [
        "lol", "lmao", "lmfao", "rofl", "haha", "hahaha", "hehe", "hihi",
        "joke", "jokes", "comedy", "funny", "hilarious", "mazak", "majak",
        "chutkula", "hasi aa gayi", "hasi rukk", "pet pakad", "😂", "🤣",
    ],
    "sad": [
        "sad", "dukhi", "dukh", "udaas", "udas", "rona", "roya", "royi",
        "cry", "crying", "heartbroken", "dil toot", "akela", "tanha",
        "miss you", "yaad aa", "bura laga", "😢", "😭", "💔",
    ],
    "angry": [
        "angry", "gussa", "irritate", "irritated", "hate", "nafrat",
        "bakwas band", "chid", "frustrat", "annoyed", "pareshan kar",
        "😡", "🤬",
    ],
    "love": [
        "love", "pyar", "pyaar", "ishq", "mohabbat", "cute", "sweet",
        "propose", "shaadi", "crush", "❤️", "😍", "🥰", "💕", "💖",
    ],
    "shock": [
        "wow", "omg", "what the", "kya baat", "hairan", "shocked",
        "shocking", "unbelievable", "vishwas nahi", "dimag ghum",
        "😱", "😲", "🤯",
    ],
    "congrats": [
        "congratulations", "congrats", "badhai", "mubarak", "won",
        "jeeta", "jeet gaya", "jeet gayi", "selected", "promotion",
        "success", "achievement", "पास हो", "🎉", "🏆",
    ],
    "greeting": [
        "good morning", "good night", "gm", "gn", "namaste", "namaskar",
        "suprabhat", "shubh ratri", "hello", "hi ", "hii", "hey",
    ],
}

MOOD_REACTIONS = {
    "funny": [
        "😂", "🤣", "😁", "👏", "🔥", "🤡", "💀", "😹", "🙈", "🙉",
        "🙊", "🤦", "🤷", "🤦‍♂️", "🤷‍♂️", "😆", "😅", "🫠",
    ],
    "sad": [
        "😢", "🥺", "💔", "🥹", "😞", "🙁", "😔", "😐", "😑",
        "🥱", "😩", "😥", "🫠", "😭",
    ],
    "angry": [
        "😡", "🤬", "👿", "👺", "👹", "😈", "👎", "✊", "👊",
        "🤛", "🤜", "🤮", "🤢", "😤",
    ],
    "love": [
        "❤️", "😍", "🥰", "💕", "💖", "💗", "💓", "💞", "💌",
        "💘", "💝", "❤️‍🔥", "💋", "🖤", "💜", "💙", "💚", "💛",
        "🧡", "🤍", "🤎", "🩷", "🩵", "🩶",
    ],
    "shock": [
        "😱", "😲", "🤯", "👀", "😮", "😯", "😬", "🤐", "😳",
        "🫢", "😵", "🤔",
    ],
    "congrats": [
        "🎉", "🎊", "🏆", "🥇", "👑", "💎", "🎁", "🎈", "🚀",
        "🎯", "🥳", "✨", "🌟", "⭐", "💯", "🤩", "🫡", "🫶",
    ],
    "greeting": [
        "🙏", "😁", "🔥", "🤗", "🤝", "✋", "🖐️", "👋", "✌️",
        "🤞", "🤟", "🤘", "🤙", "👍", "🙋", "🙋‍♂️", "👌",
    ],
}

# Agar koi mood match nahi hota, isi general pool se ek positive-safe emoji milega
DEFAULT_REACTIONS = [
    "👍", "❤️", "🔥", "🥰", "👏", "😁", "🤩", "🫡", "🫶", "🙏",
    "😍", "💯", "🤝", "🤗", "😎", "✨", "🌟", "⭐", "🎉", "🥳",
    "🤔", "😌", "🙌", "💪", "👌",
]

_WORD_RE = re.compile(r"\s+")


def _detect_mood(text: str) -> str | None:
    """Text ke andar keywords dhoondh kar sabse zyada match wala mood return karta hai."""
    if not text:
        return None
    lowered = text.lower()

    best_mood, best_score = None, 0
    for mood, keywords in MOOD_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lowered)
        if score > best_score:
            best_mood, best_score = mood, score
    return best_mood


def pick_reaction(msg) -> str:
    """Message ke content (text/caption/sticker emoji) dekh kar sahi mood wala
    reaction chunta hai. Kuch match na ho toh general pool se fallback karta hai.
    """
    text = msg.text or msg.caption or ""

    # Sticker khud hi apna emoji carry karta hai (jaise 😂 wala sticker) — use it directly
    sticker_emoji = getattr(getattr(msg, "sticker", None), "emoji", None)
    if sticker_emoji:
        mood = _detect_mood(sticker_emoji)
        if mood:
            return random.choice(MOOD_REACTIONS[mood])

    mood = _detect_mood(text)
    if mood:
        return random.choice(MOOD_REACTIONS[mood])

    return random.choice(DEFAULT_REACTIONS)


async def cmd_autoreact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("Ye command sirf group me kaam karta hai.")
        return
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Sirf admins hi autoreact on/off kar sakte hain.")
        return

    if not context.args or context.args[0].lower() not in ("on", "off"):
        state = "ON" if await store.get_autoreact(chat.id) else "OFF"
        await update.message.reply_text(
            f"🤖 Autoreact abhi: <b>{state}</b>\n"
            "Use: /autoreact on ya /autoreact off"
        )
        return

    mode = context.args[0].lower()
    await store.set_autoreact(chat.id, mode == "on")
    if mode == "on":
        await update.message.reply_text(
            "🤖 <b>Autoreact ON!</b>\n"
            "Ab main message ka mood samajh kar reaction lagaunga 😎\n"
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
    if not await store.get_autoreact(chat.id):
        return False
    if random.random() < 0.01:  # flood se bachne ke liye 1% skip
        return False
    # NOTE: incoming Message objects from python-telegram-bot don't carry a
    # `.reactions` field (that only exists on the separate MessageReactionUpdated
    # update type), so checking msg.reactions here always threw AttributeError
    # and crashed autoreact on every single message. Removed — nothing to check.

    emoji = pick_reaction(msg)
    try:
        await msg.set_reaction(emoji)
    except Exception as e:
        logger.info("Autoreact skip (%s): %s", chat.id, e)
        return False
    return False
