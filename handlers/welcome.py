from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin


async def cmd_setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args:
        await update.message.reply_text("Use karo: /setwelcome <message text>")
        return
    text = " ".join(context.args)
    db.set_welcome(update.effective_chat.id, text)
    await update.message.reply_text("✅ Welcome message set ho gaya (captcha solve hone ke baad ye dikhega).")
