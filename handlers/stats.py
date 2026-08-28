from telegram import Update
from telegram.ext import ContextTypes

import database as db


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    s = db.get_stats(chat_id)
    filters_count = len(db.get_filters(chat_id))
    notes_count = len(db.list_notes(chat_id))
    leaderboard = db.get_leaderboard(chat_id, limit=1)

    top_line = "N/A"
    if leaderboard:
        try:
            member = await context.bot.get_chat_member(chat_id, leaderboard[0]["user_id"])
            top_line = f"{member.user.mention_html()} ({leaderboard[0]['xp']} XP)"
        except Exception:
            top_line = f"User {leaderboard[0]['user_id']} ({leaderboard[0]['xp']} XP)"

    text = (
        "📊 <b>Group Stats</b>\n\n"
        f"Tracked messages: {s['total_messages']}\n"
        f"Commands used: {s['commands_used']}\n"
        f"Banned-word filters: {filters_count}\n"
        f"Saved notes: {notes_count}\n"
        f"Top XP member: {top_line}"
    )
    await update.message.reply_text(text, parse_mode="HTML")
