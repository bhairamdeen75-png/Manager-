import re
from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin

HASHTAG_REGEX = re.compile(r"#(\w+)")


async def cmd_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args:
        await update.message.reply_text("Use karo: /save <name> <content>  (ya kisi message pe reply karke /save <name>)")
        return
    name = context.args[0]
    msg = update.effective_message
    if msg.reply_to_message and len(context.args) == 1:
        content = msg.reply_to_message.text or msg.reply_to_message.caption or ""
    else:
        content = " ".join(context.args[1:])
    if not content:
        await update.message.reply_text("Note ka content nahi mila.")
        return
    db.add_note(update.effective_chat.id, name, content)
    await update.message.reply_text(f"✅ Note '#{name.lower()}' save ho gaya.")


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args:
        await update.message.reply_text("Use karo: /clear <name>")
        return
    db.remove_note(update.effective_chat.id, context.args[0])
    await update.message.reply_text(f"🗑️ Note '#{context.args[0].lower()}' hata diya.")


async def cmd_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = db.list_notes(update.effective_chat.id)
    if not names:
        await update.message.reply_text("Is group me koi notes saved nahi hain.")
        return
    await update.message.reply_text("📝 Saved notes:\n" + "\n".join(f"#{n}" for n in names))


async def check_note_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Runs on every group text message — replies with the note if a #hashtag matches."""
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not msg.text or chat.type not in ("group", "supergroup"):
        return
    for match in HASHTAG_REGEX.finditer(msg.text):
        content = db.get_note(chat.id, match.group(1))
        if content:
            await msg.reply_text(content)
            return
