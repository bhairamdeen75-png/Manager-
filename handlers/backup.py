"""Backup & Restore — notes, filters, settings, warns JSON export/import.

/backup — reply: poora group config JSON file owner ko DM.
/restore — JSON file ko group me upload karo, bot sab import kar lega.
Group migrate / naya group setup karte waqt lifesaver.
"""

import json
import logging
from telegram import Update
from telegram.error import Forbidden
from telegram.ext import ContextTypes, filters

import database as db
from handlers.utils import is_admin

logger = logging.getLogger(__name__)


async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi /backup use kar sakte hain.")
        return
    chat = update.effective_chat
    data = db.export_group_data(chat.id)
    if not data:
        await update.message.reply_text("Is group ka koi data nahi mila.")
        return
    import io
    buf = io.BytesIO(json.dumps(data, indent=2, default=str).encode())
    buf.name = f"backup_{chat.id}.json"
    try:
        await update.effective_user.send_document(buf)
        await update.message.reply_text("✅ Backup tumhe DM me bhej diya!")
    except Forbidden:
        await update.message.reply_text("❌ Pehle bot ko DM me /start karo, phir /backup.")
