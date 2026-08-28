import re

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from config import MAX_WARNS
from handlers.utils import is_admin
from handlers.logs import log_action

LINK_REGEX = re.compile(
    r"(https?://\S+|t\.me/\S+|telegram\.me/\S+|www\.\S+\.\S+|\S+\.(?:com|net|org|xyz|io|co|gg|ly|me|in|info|biz|click)\S*)",
    re.IGNORECASE,
)
MENTION_REGEX = re.compile(r"@\w{4,}")

# Known short-link / invite domains commonly abused by spammers & scammers
SCAM_DOMAINS = [
    "t.me", "telegram.me", "bit.ly", "tinyurl.com", "wa.me", "discord.gg",
    "cutt.ly", "is.gd", "rebrand.ly", "shorturl.at", "rb.gy", "linktr.ee",
    "chat.whatsapp.com", "u.to", "clck.ru",
]

# Common scam / spam phrases (kept short & broad on purpose — this is a signal,
# not a sole trigger, so it works together with the link/mention checks)
SCAM_PHRASES = [
    "free followers", "claim your gift", "click here to claim", "double your money",
    "guaranteed profit", "investment doubling", "airdrop claim", "wallet seed phrase",
    "earn from home daily", "work from home earn",
]

# Word-based obfuscations people use to dodge simple link filters,
# e.g. "t (dot) me", "t[dot]me", "bit dot ly"
_DOT_OBFUSCATION = re.compile(r"\s*[\[\(]?\s*dot\s*[\]\)]?\s*", re.IGNORECASE)
_AT_OBFUSCATION = re.compile(r"[\[\(]\s*at\s*[\]\)]", re.IGNORECASE)

MEDIA_TYPES = ["photo", "video", "sticker", "gif", "voice", "document", "audio"]


def _normalize(text: str) -> str:
    """Collapses common obfuscation tricks (spaced-out dots, '(dot)', '[dot]',
    extra whitespace between characters) so hidden links become detectable."""
    t = text.lower()
    t = _DOT_OBFUSCATION.sub(".", t)
    t = _AT_OBFUSCATION.sub("@", t)
    # collapse "t . me" / "t .me" / "t. me" style spacing around dots and slashes
    t = re.sub(r"\s*\.\s*", ".", t)
    t = re.sub(r"\s*/\s*", "/", t)
    return t


def _stripped(text: str) -> str:
    """Removes all whitespace, catching cases like 't e l e g r a m . m e'."""
    return re.sub(r"\s+", "", text)


def contains_obfuscated_link_or_scam(text: str) -> bool:
    normalized = _normalize(text)
    stripped = _stripped(normalized)
    combined = f"{text.lower()} {normalized} {stripped}"

    if LINK_REGEX.search(combined) or MENTION_REGEX.search(stripped):
        return True
    if any(domain in stripped for domain in SCAM_DOMAINS):
        return True
    if any(phrase in text.lower() or phrase in normalized for phrase in SCAM_PHRASES):
        return True
    return False


# ---------------- Commands ----------------

async def cmd_setlinkblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Use karo: /setlinkblock on|off")
        return
    enabled = context.args[0].lower() == "on"
    db.set_link_block(update.effective_chat.id, enabled)
    state = "ON ✅" if enabled else "OFF ❌"
    await update.message.reply_text(f"🔗 Link/username blocker: {state}\n(Admins is rule se exempt hain)")


async def cmd_restrictmedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/restrictmedia photo video sticker ... | all | none"""
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args:
        current = db.get_media_restrict(update.effective_chat.id)
        text = ", ".join(current) if current else "koi nahi"
        await update.message.reply_text(
            f"Abhi restricted: {text}\n\n"
            f"Use karo: /restrictmedia photo video sticker gif voice document audio\n"
            f"Available types: {', '.join(MEDIA_TYPES)}\n"
            f"/restrictmedia all — sab restrict\n"
            f"/restrictmedia none — sab allow"
        )
        return

    args = [a.lower() for a in context.args]
    if args == ["none"]:
        db.set_media_restrict(update.effective_chat.id, "")
        await update.message.reply_text("✅ Media restrictions clear kar di.")
        return
    if args == ["all"]:
        db.set_media_restrict(update.effective_chat.id, ",".join(MEDIA_TYPES))
        await update.message.reply_text("✅ Sab media types restrict kar diye.")
        return

    valid = [a for a in args if a in MEDIA_TYPES]
    if not valid:
        await update.message.reply_text(f"Valid types do: {', '.join(MEDIA_TYPES)}")
        return
    db.set_media_restrict(update.effective_chat.id, ",".join(valid))
    await update.message.reply_text(f"✅ Restricted media types: {', '.join(valid)}")


# ---------------- Passive checks (run on every group message) ----------------

async def check_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Returns True if the message was deleted (so caller can stop further checks)."""
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not msg or not msg.text or chat.type not in ("group", "supergroup"):
        return False
    if not db.get_link_block(chat.id):
        return False
    if await is_admin(update, context):
        return False

    has_link = contains_obfuscated_link_or_scam(msg.text)
    if not has_link and msg.entities:
        for ent in msg.entities:
            if ent.type in ("url", "text_link", "mention", "text_mention"):
                has_link = True
                break

    if not has_link:
        return False

    try:
        await msg.delete()
    except Exception:
        pass

    count = db.add_warn(chat.id, user.id)
    if count >= MAX_WARNS:
        db.reset_warns(chat.id, user.id)
        try:
            await context.bot.ban_chat_member(chat.id, user.id)
            await context.bot.send_message(
                chat.id,
                f"⛔ {user.mention_html()} ko baar baar links/username bhejne par ban kar diya.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await log_action(context, chat.id, f"⛔ Banned {user.mention_html()} (repeated links).")
    else:
        try:
            await context.bot.send_message(
                chat.id,
                f"🔗 {user.mention_html()}, links/usernames allowed nahi hain. Warning {count}/{MAX_WARNS}.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await log_action(context, chat.id, f"🔗 Deleted link message from {user.mention_html()}.")

    return True


async def check_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Returns True if the message was deleted."""
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not msg or chat.type not in ("group", "supergroup"):
        return False
    restricted = db.get_media_restrict(chat.id)
    if not restricted:
        return False
    if await is_admin(update, context):
        return False

    sent_type = None
    if msg.photo:
        sent_type = "photo"
    elif msg.video:
        sent_type = "video"
    elif msg.sticker:
        sent_type = "sticker"
    elif msg.animation:
        sent_type = "gif"
    elif msg.voice:
        sent_type = "voice"
    elif msg.document:
        sent_type = "document"
    elif msg.audio:
        sent_type = "audio"

    if not sent_type or sent_type not in restricted:
        return False

    try:
        await msg.delete()
    except Exception:
        pass
    try:
        await context.bot.send_message(
            chat.id,
            f"🚫 {user.mention_html()}, '{sent_type}' bhejna is group me allowed nahi hai.",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await log_action(context, chat.id, f"🚫 Deleted restricted media ({sent_type}) from {user.mention_html()}.")
    return True
