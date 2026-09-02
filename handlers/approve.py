"""/approve — trusted user: anti-spam, captcha-wait, link-block, channel-spam sab exempt.
/unapprove — hatao. /approved — list."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers import store
from handlers.utils import is_admin

logger = logging.getLogger(__name__)


async def cmd_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    msg = update.effective_message
    target = None
    if msg.reply_to_message and msg.reply_to_message.from_user:
        target = msg.reply_to_message.from_user
    elif context.args and context.args[0].lstrip("-").isdigit():
        uid = int(context.args[0])
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, uid)
            target = member.user
        except Exception:
            target = None
            store.add_approved(update.effective_chat.id, uid, str(uid))
    if not target:
        await msg.reply_text("Kisi user pe reply karke /approve, ya /approve <user_id>")
        return
    store.add_approved(update.effective_chat.id, target.id, target.first_name)
    await msg.reply_text(f"✅ {target.mention_html()} ab trusted hai — sab filters exempt.", parse_mode="HTML")


async def cmd_unapprove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    msg = update.effective_message
    if msg.reply_to_message and msg.reply_to_message.from_user:
        store.remove_approved(update.effective_chat.id, msg.reply_to_message.from_user.id)
        await msg.reply_text("🧹 Unapproved.")
    elif context.args and context.args[0].lstrip("-").isdigit():
        store.remove_approved(update.effective_chat.id, int(context.args[0]))
        await msg.reply_text("🧹 Unapproved.")
    else:
        await msg.reply_text("Reply karke ya /unapprove <user_id>")


async def cmd_approved(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = store.get_approved(update.effective_chat.id)
    if not users:
        await update.message.reply_text("Koi approved user nahi.")
        return
    lines = ["✅ **Approved users:**"] + [
        f"• {u.get('name', u['user_id'])} (`{u['user_id']}`)" for u in users
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
