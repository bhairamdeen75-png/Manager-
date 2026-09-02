import logging
import random

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from config import (
    XP_MIN_PER_MESSAGE,
    XP_MAX_PER_MESSAGE,
    XP_COOLDOWN_SECONDS,
    LEADERBOARD_INTERVAL_MINUTES,
)

logger = logging.getLogger(__name__)


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


def _build_leaderboard_text(rows) -> str:
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 <b>XP Leaderboard</b>\n"]
    for i, row in enumerate(rows):
        prefix = medals[i] if i < 3 else f"{i + 1}."
        lines.append(f"{prefix} <a href='tg://user?id={row['user_id']}'>User {row['user_id']}</a> — {row['xp']} XP")
    return "\n".join(lines)


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


# ---------------- Hourly auto-post leaderboard ----------------

async def post_hourly_leaderboards(context: ContextTypes.DEFAULT_TYPE):
    """Har LEADERBOARD_INTERVAL_MINUTES me har active XP group me leaderboard post karta hai."""
    chat_ids = db.get_xp_chats()
    for chat_id in chat_ids:
        rows = db.get_leaderboard(chat_id, limit=10)
        if not rows:
            continue
        text = _build_leaderboard_text(rows)
        try:
            # Top 3 ko asli naam dena hai to get_chat_member karo, warna fallback id link
            medals = ["🥇", "🥈", "🥉"]
            lines = ["🏆 <b>XP Leaderboard</b> (auto-update)\n"]
            for i, row in enumerate(rows):
                try:
                    member = await context.bot.get_chat_member(chat_id, row["user_id"])
                    name = member.user.mention_html()
                except Exception:
                    name = f"<a href='tg://user?id={row['user_id']}'>User {row['user_id']}</a>"
                prefix = medals[i] if i < 3 else f"{i + 1}."
                lines.append(f"{prefix} {name} — {row['xp']} XP")
            await context.bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
        except Exception as e:
            # Group me bhej nahi paye (kick out / rights issue) — chup chap skip
            logger.debug("Hourly leaderboard fail for %s: %s", chat_id, e)
