import re
import time
from telegram import Update
from telegram.ext import ContextTypes

DURATION_REGEX = re.compile(r"^(\d+)([smhd])$")
UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_duration(text: str):
    match = DURATION_REGEX.match(text.lower())
    if not match:
        return None
    value, unit = match.groups()
    return int(value) * UNIT_SECONDS[unit]


async def cmd_remindme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/remindme <10m|2h|1d> <text>"""
    if len(context.args) < 2:
        await update.message.reply_text("Use karo: /remindme <10m|2h|1d> <reminder text>")
        return
    seconds = _parse_duration(context.args[0])
    if not seconds:
        await update.message.reply_text("Time format galat hai. Use karo: 30s, 10m, 2h, 1d.")
        return

    text = " ".join(context.args[1:])
    chat_id = update.effective_chat.id
    user = update.effective_user

    await update.message.reply_text(f"⏰ Theek hai, {seconds // 60 if seconds >= 60 else seconds}{'min' if seconds>=60 else 'sec'} me yaad dilaunga.")
    context.job_queue.run_once(
        _send_reminder, seconds,
        data={"chat_id": chat_id, "user_id": user.id, "text": text},
        name=f"remind_{chat_id}_{user.id}_{int(time.time())}",
    )


async def _send_reminder(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    try:
        await context.bot.send_message(
            data["chat_id"],
            f"⏰ <a href='tg://user?id={data['user_id']}'>\u2063reminder</a> Reminder: {data['text']}",
            parse_mode="HTML",
        )
    except Exception:
        pass
