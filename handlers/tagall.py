import asyncio
from telegram import Update
from telegram.ext import ContextTypes

import database as db
from config import TAGALL_CHUNK_SIZE
from handlers.utils import is_admin


async def cmd_tagall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mentions everyone the bot has *seen* messaging in this group (Bot API can't
    list all group members directly, so this list grows as people chat)."""
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return

    users = db.get_seen_users(update.effective_chat.id)
    if not users:
        await update.message.reply_text("Abhi tak koi active members track nahi hue. Members ke chat karne ke baad try karo.")
        return

    reason = " ".join(context.args) if context.args else ""
    chunks = [users[i:i + TAGALL_CHUNK_SIZE] for i in range(0, len(users), TAGALL_CHUNK_SIZE)]

    for chunk in chunks:
        mentions = " ".join(f'<a href="tg://user?id={u["user_id"]}">\u2063{u["first_name"] or "user"}</a>' for u in chunk)
        text = f"{mentions}"
        if reason:
            text = f"{mentions}\n{reason}"
        try:
            await context.bot.send_message(update.effective_chat.id, text, parse_mode="HTML")
        except Exception:
            pass
        await asyncio.sleep(0.5)
