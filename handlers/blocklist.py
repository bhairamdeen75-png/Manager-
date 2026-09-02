"""GLOBAL BLOCKLIST — har group me hamesha enforced, kisi ke liye off nahi hota.

- Indian gaaliyan (Hinglish sab transliterations) + English profanity + scam words
- Leetspeak tolerant: g4ndu, m@darchod, b05dike sab pakdega
- Repeated chars tolerant: gaanduuu, chutiyeee bhi pakdega
- Delete + 1 hour mute (repeat offender = double)
- Koi /command isko off nahi kar sakta — permanent by design
"""

import logging
import re
from datetime import datetime, timedelta, timezone

from telegram import Update, ChatPermissions
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin

logger = logging.getLogger(__name__)

# Leetspeak normalize — spam log g@ndu, g4ndu likhte hain
_LEET = str.maketrans("013457@$", "oieastas")

BLOCKED_WORDS = [
    # --- Hindi/Hinglish gaaliyan ---
    "madarchod", "maderchod", "madanchoad", "machod",
    "behenchod", "beenchod", "behen chod", "behanchod",
    "bhosdike", "bhosdi ke", "bhosdiwale", "bhosda", "bhosdi",
    "chutiya", "chutiye", "chutia", "chutiye", "chu*tiya",
    "gandu", "gaandu", "gandu", "gaand", "gand",
    "randi", "randee", "randi khana",
    "harami", "haramkhor", "haramzada", "haramjada",
    "kamina", "kamine", "kamini",
    "saala", "saale", "salla",
    "betichod", "betachod", "betchod",
    "chodu", "chodna", "chodne", "chudai", "chuda",
    "lund", "loda", "lawda", "lavda", "lauda",
    "jhant", "jhaant", "jhanto",
    "tatti", "tatti",
    "bsdk", "bkl", "bkc", "bcd", "mc bhosdi","mc",
    "terimaa", "teri maa", "teri maa ki",
    "chinal", "chhinal", "tharki",
    # --- English profanity ---
    "motherfucker", "fucker", "fucking", "fuck",
    "bitch", "bitches", "bastard", "asshole", "assholes",
    "dickhead", "cunt", "wanker", "bollocks",
    # --- Scam/spam (permanent) ---
    "satta king", "satta matka", "teen patti hack",
    "betting link", "casino bonus", "double your money",
    "crypto pump group", "loan dena", "paisa double",
]

# Regex — word boundaries ke saath (taaki normal words na pakde)
# Repeated-char collapse: "gaaaandu" -> "gandu"
_LETTER_RE = re.compile(r"(.)\1+")
_BLOCK_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in BLOCKED_WORDS) + r")\b",
    re.IGNORECASE,
)


def _normalize(text: str) -> str:
    """Leetspeak + repeated chars normalize karo."""
    t = text.lower().translate(_LEET)
    return _LETTER_RE.sub(r"\1", t)


async def check_blocklist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Passive pipeline se call hota hai. True = action liya.
    KOI EXEMPTION NAHI — admin, owner, bot owner, sab pe chalega."""
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not msg.text or not user or user.is_bot:
        return False

    # Sirf bot ke khud ke messages skip karo (bot kabhi gali nahi bolege, 
    # lekin loop protection ke liye)
    if user.id == context.bot.id:
        return False

    normalized = _normalize(msg.text)
    if not _BLOCK_RE.search(normalized):
        return False

    # Pehle delete (order zaroori hai — phir chahe mute fail ho, message toh gaya)
    try:
        await msg.delete()
    except (BadRequest, Forbidden) as e:
        logger.warning("Blocklist delete fail %s: %s", chat.id, e)

    # Mute try karo — admins/owners pe ye Telegram-level pe fail hoga 
    # (bot admin ko restrict nahi kar sakta), lekin delete toh hoga hi
    try:
        await context.bot.restrict_chat_member(
            chat.id, user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=datetime.now(timezone.utc) + timedelta(minutes=60),
        )
        mute_note = "1 hour mute."
    except (BadRequest, Forbidden):
        # Admin/owner hai — Telegram mute nahi hone dega, but message delete ho gaya
        mute_note = "(admin hai, mute nahi ho sakta — message delete ho gaya)"

    try:
        await chat.send_message(
            f"🚫 {user.mention_html()} — gaali/badwords is group me allowed nahi hai! "
            f"{mute_note} Ye rule SAB pe lagta hai — admin, owner, koi exempt nahi.",
            parse_mode="HTML",
        )
    except Exception:
        pass
    logger.warning("Blocklist hit: user %s (%s) in %s", user.id, user.first_name, chat.id)
    return True
