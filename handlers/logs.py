from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin


async def cmd_setlogchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/setlogchannel <channel_id> — admin log channel set karo.
    Bot ko us channel me admin add karna zaroori hai."""
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args:
        await update.message.reply_text(
            "Use karo: /setlogchannel <channel_id>\n\n"
            "Channel ka ID pata karne ke liye bot ko us channel me admin banao, "
            "phir wahan koi message forward karke @userinfobot se ID le lo (ya -100 se shuru hota hai)."
        )
        return
    try:
        channel_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Valid channel_id do (jaise -1001234567890).")
        return

    try:
        await context.bot.send_message(channel_id, "✅ Ye channel ab is group ka admin-log channel hai.")
    except Exception:
        await update.message.reply_text(
            "❌ Us channel me message nahi bhej paya. Bot ko wahan admin banao aur ID check karo."
        )
        return

    db.set_log_channel(update.effective_chat.id, channel_id)
    await update.message.reply_text("✅ Admin log channel set ho gaya.")


async def cmd_removelogchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    db.set_log_channel(update.effective_chat.id, None)
    await update.message.reply_text("✅ Admin log channel hata diya gaya.")


async def log_action(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str):
    """Sends a plain-text log line to the group's configured log channel, if any."""
    log_channel_id = db.get_log_channel(chat_id)
    if not log_channel_id:
        return
    try:
        await context.bot.send_message(log_channel_id, text, parse_mode="HTML")
    except Exception:
        pass
