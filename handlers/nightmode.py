from datetime import time as dtime, timezone

from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin

_UNMUTED_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
)
_MUTED_PERMISSIONS = ChatPermissions(can_send_messages=False)


def _parse_hhmm(text: str):
    try:
        h, m = text.strip().split(":")
        return dtime(hour=int(h), minute=int(m), tzinfo=timezone.utc)
    except Exception:
        return None


def _job_name(chat_id: int, suffix: str) -> str:
    return f"nightmode_{suffix}_{chat_id}"


def schedule_night_jobs(context: ContextTypes.DEFAULT_TYPE, chat_id: int, start: str, end: str):
    """(Re)schedules the daily mute/unmute jobs for a chat's night mode."""
    for suffix in ("start", "end"):
        for job in context.job_queue.get_jobs_by_name(_job_name(chat_id, suffix)):
            job.schedule_removal()

    start_t = _parse_hhmm(start)
    end_t = _parse_hhmm(end)
    if not start_t or not end_t:
        return

    context.job_queue.run_daily(
        _night_start, start_t, chat_id=chat_id, name=_job_name(chat_id, "start"), data={"chat_id": chat_id}
    )
    context.job_queue.run_daily(
        _night_end, end_t, chat_id=chat_id, name=_job_name(chat_id, "end"), data={"chat_id": chat_id}
    )


def unschedule_night_jobs(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    for suffix in ("start", "end"):
        for job in context.job_queue.get_jobs_by_name(_job_name(chat_id, suffix)):
            job.schedule_removal()


async def _night_start(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    if not db.get_night_mode(chat_id):
        return
    try:
        await context.bot.set_chat_permissions(chat_id, _MUTED_PERMISSIONS)
        await context.bot.send_message(chat_id, "🌙 Night mode ON — ab sirf admins hi message bhej sakte hain. Good night!")
    except Exception:
        pass


async def _night_end(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    if not db.get_night_mode(chat_id):
        return
    try:
        await context.bot.set_chat_permissions(chat_id, _UNMUTED_PERMISSIONS)
        await context.bot.send_message(chat_id, "☀️ Good morning! Night mode OFF — chat khul gayi.")
    except Exception:
        pass


def schedule_all_night_modes(application):
    """Called once on bot startup to re-arm night mode jobs for every group that has it enabled."""
    for row in db.get_all_night_mode_chats():
        chat_id = row["chat_id"]
        start_t = _parse_hhmm(row["night_start"])
        end_t = _parse_hhmm(row["night_end"])
        if not start_t or not end_t:
            continue
        application.job_queue.run_daily(
            _night_start, start_t, chat_id=chat_id, name=_job_name(chat_id, "start"), data={"chat_id": chat_id}
        )
        application.job_queue.run_daily(
            _night_end, end_t, chat_id=chat_id, name=_job_name(chat_id, "end"), data={"chat_id": chat_id}
        )


# ---------------- Commands ----------------

async def cmd_nightmode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args or context.args[0].lower() not in ("on", "off"):
        start, end = db.get_night_time(update.effective_chat.id)
        await update.message.reply_text(
            f"Use karo: /nightmode on|off\n"
            f"Current schedule (UTC): {start} - {end}\n"
            f"Time badalne ke liye: /setnighttime HH:MM HH:MM"
        )
        return

    chat_id = update.effective_chat.id
    enabled = context.args[0].lower() == "on"
    db.set_night_mode(chat_id, enabled)

    if enabled:
        start, end = db.get_night_time(chat_id)
        schedule_night_jobs(context, chat_id, start, end)
        await update.message.reply_text(f"🌙 Night mode ON kar diya. Schedule (UTC): {start} - {end}")
    else:
        unschedule_night_jobs(context, chat_id)
        await update.message.reply_text("☀️ Night mode OFF kar diya.")


async def cmd_setnighttime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Use karo: /setnighttime HH:MM HH:MM  (UTC time, jaise 23:00 06:00)")
        return
    start, end = context.args
    if not _parse_hhmm(start) or not _parse_hhmm(end):
        await update.message.reply_text("Time format galat hai. Use karo HH:MM (24-hour, UTC).")
        return

    chat_id = update.effective_chat.id
    db.set_night_time(chat_id, start, end)
    if db.get_night_mode(chat_id):
        schedule_night_jobs(context, chat_id, start, end)
    await update.message.reply_text(f"✅ Night mode schedule set: {start} - {end} (UTC)")
