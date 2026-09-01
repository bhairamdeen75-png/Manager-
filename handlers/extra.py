import time
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin
from config import OWNER_IDS

BOT_START_TIME = datetime.now()


async def cmd_purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/purge — reply karke us message se leke current tak sab delete."""
    if not await is_admin_check(update, context):
        return
    msg = update.effective_message
    if not msg.reply_to_message:
        await msg.reply_text("Kisi message pe reply karke /purge likho — wahi se ab tak sab delete hoga.")
        return

    start_id = msg.reply_to_message.message_id
    end_id = msg.message_id
    total = end_id - start_id + 1

    if total > 100:
        await msg.reply_text("Ek baar me max 100 messages purge kar sakte hain.")
        return

    ids = list(range(start_id, end_id + 1))
    deleted = 0
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        try:
            await context.bot.delete_messages(msg.chat_id, chunk)
        except Exception:
            for mid in ids[i:i + 50]:
                try:
                    await context.bot.delete_message(msg.chat_id, mid)
                except Exception:
                    pass
    await msg.reply_text(f"🧹 {total} messages purge ho gaye.")


async def is_admin_check(update, context):
    from handlers.utils import is_admin
    if not await is_admin(update, context):
        await update.effective_message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return False
    return True


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/report (reply karke) — admins ko alert bhejta hai"""
    msg = update.effective_message
    if not msg.reply_to_message:
        await msg.reply_text("Jis message ki complaint hai us pe reply karke /report likho.")
        return
    if msg.reply_to_message.from_user and msg.reply_to_message.from_user.id == context.bot.id:
        return

    try:
        admins = await context.bot.get_chat_administrators(msg.chat_id)
    except Exception:
        return
    mentions = " ".join(
        a.user.mention_html() for a in admins if not a.user.is_bot
    )
    await msg.reply_text(
        f"🚨 <b>Report!</b>\n{msg.from_user.mention_html()} ne is message ki complaint ki hai:\n\n"
        f"> {msg.reply_to_message.text or '(media message)'}\n\n{mentions}",
        parse_mode="HTML",
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status — bot health check (sirf owners ke liye)"""
    if update.effective_user.id not in OWNER_IDS:
        return

    lines = ["🩺 <b>Bot Health</b>"]
    t0 = datetime.now()
    try:
        db._client.admin.command("ping")
        ms = (datetime.now() - t0).total_seconds() * 1000
        emoji = "✅" if ms < 500 else "⚠️"
        lines.append(f"{emoji} MongoDB: connected ({ms:.0f}ms)")
    except Exception as e:
        lines.append(f"❌ MongoDB: FAIL — {e}")

    uptime = datetime.now() - BOT_START_TIME
    hours, rem = divmod(int(uptime.total_seconds()), 3600)
    lines.append(f"⏱️ Uptime: {hours}h {minutes_str(rem)}")

    try:
        from handlers import captcha
        lines.append(f"🧩 Pending captchas: {len(captcha._pending)}")
    except Exception:
        pass

    jobs = len(context.job_queue.jobs())
    lines.append(f"📅 Active jobs: {jobs}")
    lines.append(f"👥 Groups: {db.get_group_count()}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


def minutes_str(seconds: int) -> str:
    return f"{seconds // 60}m"
