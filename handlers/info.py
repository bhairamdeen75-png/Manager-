from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin, get_target_user


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = get_target_user(update) or update.effective_user
    chat = update.effective_chat

    status = "member"
    try:
        member = await context.bot.get_chat_member(chat.id, target.id)
        status = member.status
    except Exception:
        pass

    warns = db.get_warns(chat.id, target.id)
    xp = db.get_xp(chat.id, target.id)

    text = (
        f"👤 <b>User Info</b>\n\n"
        f"Name: {target.mention_html()}\n"
        f"ID: <code>{target.id}</code>\n"
        f"Username: @{target.username if target.username else 'N/A'}\n"
        f"Status: {status}\n"
        f"Warnings: {warns}\n"
        f"XP: {xp}"
    )
    await update.message.reply_text(text, parse_mode="HTML")
