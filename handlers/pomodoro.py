from telegram import Update
from telegram.ext import ContextTypes

_active: dict[int, dict] = {}  # chat_id -> {"cycle": int, "cycles": int}


def _job_name(chat_id: int) -> str:
    return f"pomodoro_{chat_id}"


async def cmd_pomodoro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/pomodoro <work_min> <break_min> [cycles]"""
    args = context.args
    if not args or len(args) not in (2, 3):
        await update.message.reply_text("Use karo: /pomodoro <work_min> <break_min> [cycles]\nJaise: /pomodoro 25 5 4")
        return
    try:
        work_min, break_min = int(args[0]), int(args[1])
        cycles = int(args[2]) if len(args) == 3 else 4
    except ValueError:
        await update.message.reply_text("Numbers do (minutes aur cycles).")
        return

    chat_id = update.effective_chat.id
    _active[chat_id] = {"cycle": 1, "cycles": cycles, "work_min": work_min, "break_min": break_min}
    await update.message.reply_text(
        f"🍅 Pomodoro shuru! {cycles} cycles — {work_min} min work / {break_min} min break.\n"
        f"Cycle 1/{cycles}: Work time shuru! 💪"
    )
    context.job_queue.run_once(
        _next_phase, work_min * 60, chat_id=chat_id, name=_job_name(chat_id),
        data={"chat_id": chat_id, "phase": "break"},
    )


async def cmd_pomodorostop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    for job in context.job_queue.get_jobs_by_name(_job_name(chat_id)):
        job.schedule_removal()
    _active.pop(chat_id, None)
    await update.message.reply_text("⏹️ Pomodoro session stop kar diya.")


async def _next_phase(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id, phase = data["chat_id"], data["phase"]
    state = _active.get(chat_id)
    if not state:
        return

    if phase == "break":
        await context.bot.send_message(chat_id, f"⏰ Cycle {state['cycle']}/{state['cycles']} done! Break time 🧘 ({state['break_min']} min)")
        context.job_queue.run_once(
            _next_phase, state["break_min"] * 60, chat_id=chat_id, name=_job_name(chat_id),
            data={"chat_id": chat_id, "phase": "work"},
        )
    else:
        state["cycle"] += 1
        if state["cycle"] > state["cycles"]:
            await context.bot.send_message(chat_id, "🎉 Pomodoro session complete! Great work today.")
            _active.pop(chat_id, None)
            return
        await context.bot.send_message(chat_id, f"💪 Cycle {state['cycle']}/{state['cycles']}: Work time shuru! ({state['work_min']} min)")
        context.job_queue.run_once(
            _next_phase, state["work_min"] * 60, chat_id=chat_id, name=_job_name(chat_id),
            data={"chat_id": chat_id, "phase": "break"},
        )
