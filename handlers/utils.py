from telegram import Update
from telegram.ext import ContextTypes


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> bool:
    """Check if the given user (default: message sender) is an admin/owner of the chat."""
    chat = update.effective_chat
    uid = user_id or update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat.id, uid)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


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
