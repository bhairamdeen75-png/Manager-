"""Appeals — banned/warned user bot ko private chat me /appeal bhejta hai.
Admins ko inline approve/deny panel jata hai. Owner Panel ke logs me bhi dikhega.
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

import database as db
from handlers import store
from handlers.utils import is_admin

logger = logging.getLogger(__name__)


async def cmd_appeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Private chat me /appeal <reason> — user ke ban/warn ka review request."""
    user = update.effective_user
    chat = update.effective_chat
    if chat.type != "private":
        await update.message.reply_text("DM me aake /appeal bhejo — group me nahi.")
        return

    # Sabse recent ban jis group me hua
    group_id = store.get_ban_group(user.id)
    reason = " ".join(context.args) or "(koi reason nahi diya)"

    if not group_id:
        await update.message.reply_text(
            "Koi active ban record nahi mila. Agar abhi warn ho hai, toh warn appeal "
            "ka process group admins se baat karna hai."
        )
        return

    store.add_appeal(group_id, user.id, user.first_name, reason)

    # Group ke admins ko panel bhejo
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"appeal:approve:{group_id}:{user.id}"),
        InlineKeyboardButton("❌ Deny", callback_data=f"appeal:deny:{group_id}:{user.id}"),
    ]])
    try:
        await context.bot.send_message(
            group_id,
            f"⚖️ **Appeal!** {user.mention_html()} ({user.id}) apne ban ka review maang raha hai.\n"
            f"💬 Reason: {reason}",
            parse_mode="HTML",
            reply_markup=kb,
        )
        await update.message.reply_text(
            "✅ Appeal bhej diya! Group ke admins dekh lenge."
        )
    except Forbidden:
        await update.message.reply_text(
            "❌ Appeal group me nahi jaa paya (bot wahan se nikal gaya hai)."
        )


async def on_appeal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """pattern r'^appeal:' se register hota hai. Admin approve/deny karta hai."""
    query = update.callback_query
    data = query.data.split(":")
    _, action, group_id, target_id = data
    chat = update.effective_chat

    if not await is_admin(update, context):
        await query.answer("Sirf admins hi appeal decide kar sakte hain.", show_alert=True)
        return

    target_id = int(target_id)
    if action == "approve":
        # Unban karo
        try:
            await context.bot.unban_chat_member(int(group_id), target_id)
        except (BadRequest, Forbidden) as e:
            logger.warning("Appeal unban fail %s: %s", group_id, e)
        await query.answer("✅ Appeal approve — user unban ho gaya.")
        await query.edit_message_text(
            f"⚖️ Appeal approve ho gaya (admin: {query.from_user.mention_html()}). User unban kar diya.",
            parse_mode="HTML",
        )
        try:
            await context.bot.send_message(
                target_id, "✅ Tumhara appeal approve ho gaya! Group me wapas aa sakte ho."
            )
        except Exception:
            pass
    else:
        await query.answer("❌ Appeal deny ho gaya.")
        await query.edit_message_text(
            f"⚖️ Appeal deny (admin: {query.from_user.mention_html()}).",
            parse_mode="HTML",
        )
        try:
            await context.bot.send_message(target_id, "❌ Tumhara appeal deny ho gaya.")
        except Exception:
            pass


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast ke /cancel ko yahan handle nahi karna — panel.py already karta hai."""
    return
