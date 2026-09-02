"""/activity — 7-day message activity ka PNG chart (matplotlib, offline, free)."""

import io
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

import matplotlib
matplotlib.use("Agg")  # headless server ke liye zaroori
import matplotlib.pyplot as plt

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers import store
from handlers.utils import is_admin

logger = logging.getLogger(__name__)


async def cmd_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    chat_id = update.effective_chat.id
    docs = store.get_activity(chat_id, days=7)
    if not docs:
        await update.message.reply_text("Abhi koi activity data nahi hai (7 din ka wait karo).")
        return

    # Daily counts
    days = [(datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
    per_day = Counter()
    per_user = Counter()
    names = {}
    for d in docs:
        per_day[d["day"]] += d["count"]
        per_user[d["user_id"]] += d["count"]
        names[d["user_id"]] = d.get("name") or str(d["user_id"])

    counts = [per_day.get(day, 0) for day in days]
    labels = [day[5:] for day in days]  # MM-DD

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(labels, counts, color="#2196F3")
    ax.set_title("Last 7 days activity")
    ax.set_ylabel("Messages")
    for i, v in enumerate(counts):
        ax.text(i, v, str(v), ha="center", va="bottom")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    buf.name = "activity.png"

    top = per_user.most_common(5)
    top_lines = "\n".join(f"{i+1}. {names.get(uid, uid)} — {c} msgs" for i, (uid, c) in enumerate(top))
    await update.message.reply_photo(
        buf,
        caption=f"📊 Top 5 active users:\n{top_lines}",
    )
