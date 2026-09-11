import time

from telegram import Update
from telegram.ext import ContextTypes

# ---------------------------------------------------------------------------
# is_admin() ko har passive handler (link check, forward check, spam check,
# channelspam check, ...) alag-alag independently call karta tha — matlab EK
# hi message ke liye Telegram ko 4-5 baar getChatMember round-trip jaata tha.
# Yahi wo delay tha (5-10 sec). Ab ek chhota TTL cache: same (chat, user) ke
# liye 60 sec tak dobara Telegram ko poochna nahi padega.
# ---------------------------------------------------------------------------
_ADMIN_CACHE_TTL = 60  # seconds
_admin_cache: dict[tuple[int, int], tuple[bool, float]] = {}


async def is_admin(update, context, user_id=None):
    chat = update.effective_chat
    uid = user_id or update.effective_user.id
    key = (chat.id, uid)
    now = time.monotonic()
    cached = _admin_cache.get(key)
    if cached and cached[1] > now:
        return cached[0]

    t0 = time.monotonic()
    try:
        member = await context.bot.get_chat_member(chat.id, uid)
        result = member.status in ("administrator", "creator")
    except Exception:
        result = False
    elapsed = time.monotonic() - t0
    if elapsed > 0.3:
        import logging
        logging.getLogger(__name__).warning("SLOW get_chat_member (%.2fs)", elapsed)

    _admin_cache[key] = (result, now + _ADMIN_CACHE_TTL)
    return result


def invalidate_admin_cache(chat_id: int, user_id: int = None):
    """Promotion/demotion hone par turant purana cached result hata do,
    warna up to 60 sec tak galat status use hota rahega."""
    if user_id is not None:
        _admin_cache.pop((chat_id, user_id), None)
    else:
        for key in [k for k in _admin_cache if k[0] == chat_id]:
            _admin_cache.pop(key, None)


def get_target_user(update: Update):
    """Get the target user from a reply, if any."""
    msg = update.effective_message
    if msg.reply_to_message:
        return msg.reply_to_message.from_user
    return None

def format_welcome_leave(text: str, user, chat) -> str:
    """Welcome/leave message me placeholders replace karta hai:
    {name} {fullname} {username} {id} {date} {time} {group} {mention}"""
    from datetime import datetime, timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))  # Indian time
    now = datetime.now(ist)
    username = f"@{user.username}" if user.username else "(nahi hai)"
    fullname = user.first_name or ""
    if user.last_name:
        fullname += f" {user.last_name}"
    out = text
    replacements = {
        "{name}": user.first_name or "",
        "{fullname}": fullname,
        "{username}": username,
        "{id}": str(user.id),
        "{date}": now.strftime("%d %b %Y"),
        "{time}": now.strftime("%I:%M %p") + " IST",
        "{group}": chat.title or "",
        "{mention}": user.mention_html(),
    }
    for k, v in replacements.items():
        out = out.replace(k, v)
    return out
