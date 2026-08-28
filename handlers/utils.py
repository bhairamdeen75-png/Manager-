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
