from telegram import Update
from telegram.ext import ContextTypes

import database as db
from config import MAX_WARNS
from handlers.utils import is_admin


async def cmd_addfilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args:
        await update.message.reply_text("Use karo: /addfilter <word>")
        return
    word = " ".join(context.args)
    db.add_filter(update.effective_chat.id, word)
    await update.message.reply_text(f"✅ '{word}' filter list me add ho gaya.")


async def cmd_removefilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args:
        await update.message.reply_text("Use karo: /removefilter <word>")
        return
    word = " ".join(context.args)
    db.remove_filter(update.effective_chat.id, word)
    await update.message.reply_text(f"🗑️ '{word}' filter list se hata diya.")


async def cmd_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words = db.get_filters(update.effective_chat.id)
    if not words:
        await update.message.reply_text("Is group me koi filter set nahi hai.")
        return
    await update.message.reply_text("🔒 Filtered words:\n" + "\n".join(f"• {w}" for w in words))


async def check_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Run on every group text message. Deletes messages containing banned words."""
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if not msg or not msg.text or chat.type not in ("group", "supergroup"):
        return

    words = db.get_filters(chat.id)
    if not words:
        return

    text_lower = msg.text.lower()
    for w in words:
        if w in text_lower:
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
                        f"⛔ {user.mention_html()} ko banned word ke baar baar use karne par ban kar diya.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            else:
                try:
                    await context.bot.send_message(
                        chat.id,
                        f"🚫 {user.mention_html()}, ye word allowed nahi hai. Warning {count}/{MAX_WARNS}.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            break
