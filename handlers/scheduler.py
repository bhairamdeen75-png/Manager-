"""/schedule 2h Movie night! — bot khud post karega. Restart-proof (Mongo persist)."""

import logging
import re
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers import store
from handlers.utils import is_admin

logger = logging.getLogger(__name__)

DUR_RE = re.compile(r"^(\d+)(s|m|h|d)$")
UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def parse_duration(s):
    m = DUR_RE.match(s.lower())
    if not m:
        return None
    return timedelta(**{UNITS[m.group(2)]: int(m.group(1))})


async def run_scheduled(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    try:
        await context.bot.send_message(data["chat_id"], data["text"])
    except Exception as e:
        logger.warning("Scheduled send fail: %s", e)
    store.del_schedule(data["chat_id"], data["sched_id"])


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context) or len(context.args) < 2:
        await update.message.reply_text("Format: /schedule <time> <text>\nJaise: /schedule 2h Movie night!")
        return
    delta = parse_duration(context.args[0])
    if not delta:
        await update.message.reply_text("Time format: 30s, 10m, 2h, 1d")
        return
    # Raw text lo, pehla token (time) chhod kar — newlines preserve
    raw = update.effective_message.text.partition(" ")[2].strip()
    text = raw.partition(" ")[2].strip()   # pehla word = duration, baaki = message
    run_at = datetime.now(timezone.utc) + delta
    sched_id = str(store.add_schedule(update.effective_chat.id, run_at, text,
                                      update.effective_user.id))
    context.job_queue.run_once(run_scheduled, delta,
                               data={"chat_id": update.effective_chat.id,
                                     "text": text, "sched_id": sched_id})
    await update.message.reply_text(f"⏰ Schedule ho gaya! {delta} baad bhej dunga.")


async def cmd_scheduled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scheds = store.get_chat_schedules(update.effective_chat.id)
    if not scheds:
        await update.message.reply_text("Koi scheduled message nahi hai.")
        return
    lines = ["⏰ **Scheduled:**"]
    for s in scheds:
        lines.append(f"• `{s['_id']}` — {s['run_at']:%d %b %H:%M} UTC — {s['text'][:50]}")
    await update.message.reply_text("\n".join(lines))


async def cmd_unsched(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context) or not context.args:
        await update.message.reply_text("Format: /unsched <id>  (id /scheduled me dikhti hai)")
        return
    store.del_schedule(update.effective_chat.id, context.args[0])
    await update.message.reply_text("🧹 Schedule cancel ho gaya.")


def rearm_schedules(app):
    """bot.py startup pe call karo — restart ke baad pending schedules wapas arm karta hai."""
    now = datetime.now(timezone.utc)
    for s in store.all_pending_schedules():
        run_at = s["run_at"]
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        delay = (run_at - now).total_seconds()
        data = {"chat_id": s["chat_id"], "text": s["text"], "sched_id": str(s["_id"])}
        if delay > 0:
            app.job_queue.run_once(run_scheduled, delay, data=data)
        else:
            app.job_queue.run_once(run_scheduled, 1, data=data)  # pending — turant bhejo
