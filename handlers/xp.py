import random
from telegram import Update
from telegram.ext import ContextTypes

import database as db
from config import XP_MIN_PER_MESSAGE, XP_MAX_PER_MESSAGE, XP_COOLDOWN_SECONDS


async def award_xp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Runs on every group text message — grants a small random XP amount with a cooldown."""
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not msg or not user or chat.type not in ("group", "supergroup"):
        return
    amount = random.randint(XP_MIN_PER_MESSAGE, XP_MAX_PER_MESSAGE)
    db.add_xp(chat.id, user.id, amount, cooldown_seconds=XP_COOLDOWN_SECONDS)


async def cmd_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.utils import get_target_user
    target = get_target_user(update) or update.effective_user
    xp = db.get_xp(update.effective_chat.id, target.id)
    await update.message.reply_text(f"⭐ {target.mention_html()} ke pass {xp} XP hai.", parse_mode="HTML")


async def cmd_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_leaderboard(update.effective_chat.id, limit=10)
    if not rows:
        await update.message.reply_text("Abhi tak koi XP nahi kamaya gaya is group me.")
        return

    lines = ["🏆 <b>XP Leaderboard</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(rows):
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, row["user_id"])
            name = member.user.mention_html()
        except Exception:
            name = f"User {row['user_id']}"
        prefix = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{prefix} {name} — {row['xp']} XP")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
