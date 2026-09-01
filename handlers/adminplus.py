"""Admin+ features: /purge (bulk delete), /report (admins tag), /status (user ka full status)."""

import asyncio
from datetime import datetime, timedelta, timezone

from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin

# ---------------- /purge ----------------

async def cmd_purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply karke use karo — reply wale message se lekar ab tak ke saare
    messages delete ho jate hain (max 100, Telegram limit)."""
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi /purge use kar sakte hain.")
        return

    msg = update.effective_message
    if not msg.reply_to_message:
        await msg.reply_text("Kisi message pe reply karke /purge use karo.")
        return

    chat_id = msg.chat_id
    start_id = msg.reply_to_message.message_id
    end_id = msg.message_id  # /purge command ka khud ka message bhi delete ho jayega

    if end_id - start_id > 100:
        await msg.reply_text("Max 100 messages tak hi purge kar sakta hoon.")
        return

    deleted = 0
    for mid in range(start_id, end_id + 1):
        try:
            await context.bot.delete_message(chat_id, mid)
            deleted += 1
        except (BadRequest, Forbidden):
            pass  # 48h+ purana message ya permission nahi — skip
        await asyncio.sleep(0.05)  # rate-limit friendly

    status = await msg.reply_text(f"🧹 {deleted} messages purge kar diye.")
    await asyncio.sleep(5)
    try:
        await status.delete()
    except Exception:
        pass


# ---------------- /report ----------------

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply karke use karo — replied user ko report karta hai, saare admins ko tag karta hai."""
    msg = update.effective_message
    chat = update.effective_chat

    target = None
    if msg.reply_to_message and msg.reply_to_message.from_user:
        target = msg.reply_to_message.from_user
    if not target:
        await msg.reply_text("Kisi message pe reply karke /report use karo.")
        return
    if target.is_bot:
        await msg.reply_text("Bot ko report karna kaafi nahi 😅")
        return

    admins = await chat.get_administrators()
    tags = " ".join(a.user.mention_html() for a in admins if not a.user.is_bot)
    reason = " ".join(context.args) if context.args else ""

    text = (
        f"🚨 <b>Report!</b>\n"
        f"{target.mention_html()} ko report kiya gaya hai — {tags} dekho!\n"
    )
    if reason:
        text += f"\n💬 Reason: {reason}"
    await msg.reply_text(text, parse_mode=ParseMode.HTML)


# ---------------- /status ----------------

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply karke use karo — replied user ka Telegram status + warns + XP dikhata hai."""
    target = None
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target = update.message.reply_to_message.from_user
    if not target:
        await update.message.reply_text("Kisi user ke message pe reply karke /status use karo.")
        return

    chat_id = update.effective_chat.id
    try:
        member = await context.bot.get_chat_member(chat_id, target.id)
        status_map = {
            "creator": "👑 Group Owner",
            "administrator": "👮 Admin",
            "member": "👤 Normal Member",
            "restricted": "🔇 Restricted (mute/active restrictions)",
            "left": "👋 Group me nahi hai",
            "kicked": "⛔ Banned hai",
        }
        status = status_map.get(member.status, member.status)
        if member.status == "restricted":
            until = member.until_date
            if until and until > datetime.now(timezone.utc):
                status += f" (unmute: {until:%d %b %Y %H:%M} UTC)"
            else:
                status += " (permanent)"
    except Exception:
        status = "❓ nahi pata (bot ko info dekhne ki permission nahi)"

    warns = db.get_warns(chat_id, target.id)
    xp = db.get_xp(chat_id, target.id)

    await update.message.reply_text(
        f"📊 <b>Status</b>\n"
        f"👤 User: {target.mention_html()} (<code>{target.id}</code>)\n"
        f"📈 Status: {status}\n"
        f"⚠️ Warnings: {warns}\n"
        f"⭐ XP: {xp}",
        parse_mode=ParseMode.HTML,
    )
