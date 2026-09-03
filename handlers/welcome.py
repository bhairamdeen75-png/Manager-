from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin, format_welcome_leave

PLACEHOLDER_HELP = (
    "📌 <b>Placeholders (message me use karo):</b>\n"
    "<code>{name}</code> — pehla naam\n"
    "<code>{fullname}</code> — poora naam\n"
    "<code>{username}</code> — @username\n"
    "<code>{id}</code> — user id\n"
    "<code>{date}</code> — aaj ki date\n"
    "<code>{time}</code> — abhi ka time (IST)\n"
    "<code>{group}</code> — group ka naam\n"
    "<code>{mention}</code> — clickable mention"
)


async def cmd_setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args:
        await update.message.reply_text(
            "Use karo: /setwelcome <message text>\n\n" + PLACEHOLDER_HELP,
            parse_mode="HTML",
        )
        return
    # Raw text lo — newlines preserve rahenge (context.args newline kha jata hai)
    text = update.effective_message.text.partition(" ")[2].strip()
    db.set_welcome(update.effective_chat.id, text)
    # Preview dikhao — apna hi placeholder fill karke
    preview = format_welcome_leave(text, update.effective_user, update.effective_chat)
    await update.message.reply_text(
        "✅ Welcome message set ho gaya (captcha solve hone ke baad ye dikhega).\n\n"
        f"<b>Preview:</b>\n{preview}",
        parse_mode="HTML",
    )


async def cmd_setleave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args:
        current = db.get_leave_message(update.effective_chat.id)
        await update.message.reply_text(
            "Use karo: /setleave <message text>\n\n" + PLACEHOLDER_HELP +
            ("\n\n<i>Abhi set hai:</i> " + current if current else "\n\n<i>Abhi koi leave message nahi hai.</i>"),
            parse_mode="HTML",
        )
        return
    # Raw text lo — newlines preserve rahenge (context.args newline kha jata hai)
    text = update.effective_message.text.partition(" ")[2].strip()
    if text.lower() in ("off", "disable", "none"):
        db.set_leave_message(update.effective_chat.id, "")
        await update.message.reply_text("🧹 Leave message OFF kar diya.")
        return
    db.set_leave_message(update.effective_chat.id, text)
    preview = format_welcome_leave(text, update.effective_user, update.effective_chat)
    await update.message.reply_text(
        "✅ Leave message set ho gaya.\n\n"
        f"<b>Preview:</b>\n{preview}",
        parse_mode="HTML",
    )
