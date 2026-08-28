from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin


async def cmd_addresponse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/addresponse <trigger> | <response text>"""
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    raw = update.effective_message.text.partition(" ")[2]
    if "|" not in raw:
        await update.message.reply_text("Use karo: /addresponse trigger | response text")
        return
    trigger, _, response = raw.partition("|")
    trigger, response = trigger.strip(), response.strip()
    if not trigger or not response:
        await update.message.reply_text("Trigger aur response dono do.")
        return
    db.add_response(update.effective_chat.id, trigger, response)
    await update.message.reply_text(f"✅ Auto-response add ho gaya for '{trigger}'.")


async def cmd_delresponse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args:
        await update.message.reply_text("Use karo: /delresponse <trigger>")
        return
    trigger = " ".join(context.args)
    db.remove_response(update.effective_chat.id, trigger)
    await update.message.reply_text(f"🗑️ '{trigger}' ka auto-response hata diya.")


async def cmd_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = db.list_responses(update.effective_chat.id)
    if not items:
        await update.message.reply_text("Is group me koi auto-responses set nahi hain.")
        return
    text = "\n".join(f"• {i['trigger']}" for i in items)
    await update.message.reply_text(f"🤖 Auto-response triggers:\n{text}")


async def check_auto_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not msg.text or chat.type not in ("group", "supergroup"):
        return
    text_lower = msg.text.lower()
    for item in db.list_responses(chat.id):
        if item["trigger"] in text_lower:
            await msg.reply_text(item["response"])
            return
