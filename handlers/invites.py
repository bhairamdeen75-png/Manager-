"""Invite tracking — join-request based (100% reliable).

Kaise kaam karta hai:
- /invites → bot per-user link banata hai (creates_join_request=True)
- Member link se join request karta hai → ChatJoinRequest me invite_link.name = "inv_<inviter_id>"
- Bot request approve karta hai + inviter ka count +1
- /invitetop → leaderboard

Zaroori: bot admin ho + "Invite Users via Link" permission.
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes, ChatJoinRequestHandler

import database as db
from handlers import store
from handlers.utils import is_admin

logger = logging.getLogger(__name__)


async def cmd_invites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Ye command group me use karo.")
        return
    count = store.get_invites(chat.id, user.id)
    try:
        link = await context.bot.create_chat_invite_link(
            chat_id=chat.id, name=f"inv_{user.id}", creates_join_request=True
        )
    except (BadRequest, Forbidden):
        await update.message.reply_text(
            "❌ Bot ko 'Invite Users via Link' admin permission chahiye."
        )
        return
    store.map_link_to_inviter(chat.id, link.invite_link, user.id)
    store.set_inviter_name(chat.id, user.id, user.first_name)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Invite Link", url=link.invite_link)]])
    await update.message.reply_text(
        f"🎯 Tumhare ab tak {count} invites!\n\n"
        f"Ye link kisi ko bhejo — wo request bhejega, bot approve karega, "
        f"aur tumhara count +1 hoga.",
        reply_markup=kb,
    )


async def on_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request
    link = req.invite_link
    if not link or not link.name or not link.name.startswith("inv_"):
        return
    try:
        inviter_id = int(link.name[4:])
    except ValueError:
        return
    chat = req.chat
    user = req.from_user
    if inviter_id == user.id:
        return  # khud ko invite karke count nahi badhega
    store.inc_invite(chat.id, inviter_id, "")
    try:
        await req.approve()
    except Exception as e:
        logger.warning("Join request approve fail %s: %s", chat.id, e)
        return
    try:
        await context.bot.send_message(
            chat.id,
            f"🎉 {user.mention_html()} invite se aaya — inviter ka count +1!",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def cmd_invitetop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    top = store.top_inviters(chat.id, limit=10)
    if not top:
        await update.message.reply_text("Abhi koi invite nahi hua. /invites se shuru karo!")
        return
    lines = ["🏆 **Top Inviters**\n"]
    for i, doc in enumerate(top, 1):
        name = doc.get("name") or str(doc["user_id"])
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        lines.append(f"{medal} {name} — {doc.get('count', 0)} invites")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
