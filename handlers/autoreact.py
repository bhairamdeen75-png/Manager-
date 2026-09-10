"""AUTOREACT — bot ab message ka mood samajh kar reaction lagayega
(random ulta-sidha nahi — funny message pe hasi wala emoji, sad pe sad wala, etc).
/autoreact on / off — sirf admins.

Telegram limits ka dhyan:
- Bots sirf standard emoji reactions laga sakte hain — aur zaruri baat: Telegram
  sirf ek fixed whitelist of ~80 emoji ko hi reaction ke roop me accept karta
  hai. Koi bhi emoji jo us list me nahi (ZWJ combos jaise 🤦‍♂️/🤷‍♂️, naye
  Unicode emoji jaise 🩷🩵🩶, ya VS16 variants) reject ho jaata hai:
      "Can't parse reactiontype: field 'custom_emoji_id' must be a valid number"
  (Telegram use custom-emoji-id samajhne ki koshish karta hai aur fail hota
  hai). Isliye pools ab sirf whitelist-safe emoji use karte hain, aur agar
  phir bhi koi reject ho jaaye to ek guaranteed-safe emoji se retry hota hai.
- Flood limit se bachne ke liye har message pe react nahi karte (~99% pe karte hain)
- Agar koi mood match nahi hota toh ek safe general pool se pick karte hain
"""

import logging
import random
import re

from telegram import Update
from telegram.constants import ChatType
from telegram.error import BadRequest
from telegram.ext import ContextTypes, CommandHandler

from handlers import store
from handlers.utils import is_admin

logger = logging.getLogger(__name__)

_VS16 = "\ufe0f"


def _clean(emoji: str) -> str:
    """Variation selector-16 hata do — kai keyboards/fonts ye silently add kar
    dete hain aur Telegram ke reaction-whitelist match ko fail kara dete hain."""
    return emoji.replace(_VS16, "")


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

# Sirf Telegram ke allowed reaction-emoji whitelist wale emoji rakhe hain —
# ZWJ combos, skin-tone/gender variants, aur naye Unicode emoji jaanbujh kar
# hataye gaye hain kyunki Telegram unhe reaction ke roop me reject karta hai.
MOOD_REACTIONS = {
    "funny": ["🤣", "😁", "👏", "🤡", "🗿", "😎"],
    "sad": ["😢", "💔", "😭"],
    "angry": ["🤬", "😡", "👎"],
    "love": ["❤", "🥰", "😍", "💘", "😘", "💋"],
    "shock": ["😱", "🤯", "😨", "👀"],
    "congrats": ["🎉", "🏆", "💯", "🤩"],
    "greeting": ["🙏", "🤗", "🤝", "👌"],
}

# Agar koi mood match nahi hota, isi general pool se ek positive-safe emoji milega
DEFAULT_REACTIONS = ["👍", "❤", "🔥", "🥰", "👏", "😁", "🤩", "🙏", "😍", "💯", "🤝", "🤗", "😎", "🎉"]

# set_reaction fail ho jaaye (400 Bad Request) to inhi me se retry — ekdum
# core, sabse bharosemand emoji jo Telegram har jagah accept karta hai.
_SAFE_FALLBACK = ["👍", "❤", "🔥", "😁", "🎉"]

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
    Return hamesha VS16-clean, whitelist-safe emoji hota hai.
    """
    text = msg.text or msg.caption or ""

    # Sticker khud hi apna emoji carry karta hai (jaise 😂 wala sticker) — use it directly
    sticker_emoji = getattr(getattr(msg, "sticker", None), "emoji", None)
    if sticker_emoji:
        mood = _detect_mood(sticker_emoji)
        if mood:
            return _clean(random.choice(MOOD_REACTIONS[mood]))

    mood = _detect_mood(text)
    if mood:
        return _clean(random.choice(MOOD_REACTIONS[mood]))

    return _clean(random.choice(DEFAULT_REACTIONS))


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


async def _try_react(msg, emoji: str) -> bool:
    """Reaction lagane ki koshish. BadRequest (invalid/non-whitelisted emoji)
    aaye to ek guaranteed-safe emoji se ek dobara try karta hai, taaki ek
    galat emoji ki wajah se poora react hi skip na ho jaaye."""
    try:
        await msg.set_reaction(emoji)
        return True
    except BadRequest as e:
        logger.info("Autoreact emoji '%s' rejected (%s) — safe fallback try kar rahe hain", emoji, e)
    except Exception as e:
        logger.info("Autoreact set_reaction error: %s", e)
        return False

    fallback = _clean(random.choice([f for f in _SAFE_FALLBACK if f != emoji] or _SAFE_FALLBACK))
    try:
        await msg.set_reaction(fallback)
        return True
    except Exception as e:
        logger.info("Autoreact fallback bhi fail (%s)", e)
        return False


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
    await _try_react(msg, emoji)
    return False
