from telegram import Update
from telegram.ext import ContextTypes


def _parse_parts(update: Update):
    raw = update.effective_message.text.partition(" ")[2]
    return [p.strip() for p in raw.split("|") if p.strip()]


async def cmd_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/poll Question? | option1 | option2 | ..."""
    parts = _parse_parts(update)
    if len(parts) < 3:
        await update.message.reply_text("Use karo: /poll Question? | option1 | option2 | option3 ...")
        return
    question, options = parts[0], parts[1:10]
    await context.bot.send_poll(update.effective_chat.id, question=question, options=options, is_anonymous=True)


async def cmd_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/quiz Question? | correct_index(0-based) | option1 | option2 | ..."""
    parts = _parse_parts(update)
    if len(parts) < 4:
        await update.message.reply_text("Use karo: /quiz Question? | correct_index | option1 | option2 | ...")
        return
    question = parts[0]
    try:
        correct_index = int(parts[1])
    except ValueError:
        await update.message.reply_text("correct_index ek number hona chahiye (0 = pehla option).")
        return
    options = parts[2:10]
    if not (0 <= correct_index < len(options)):
        await update.message.reply_text("correct_index options ki range me nahi hai.")
        return
    await context.bot.send_poll(
        update.effective_chat.id, question=question, options=options,
        type="quiz", correct_option_id=correct_index, is_anonymous=True,
    )
