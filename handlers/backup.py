"""Backup & Restore — notes, filters, settings, warns JSON export/import.

/backup — group ka data JSON file me, owner/admin ko DM me bhejta hai.
/restore — JSON file pe reply karke sab import kar leta hai.
"""

import io
import json
import logging

from telegram import Update
from telegram.error import Forbidden
from telegram.ext import ContextTypes

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
    buf = io.BytesIO(json.dumps(data, indent=2, default=str).encode())
    buf.name = f"backup_{chat.id}.json"
    try:
        await update.effective_user.send_document(buf)
        await update.message.reply_text("✅ Backup tumhe DM me bhej diya!")
    except Forbidden:
        await update.message.reply_text("❌ Pehle bot ko DM me /start karo, phir /backup.")


async def cmd_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """JSON backup file pe reply karke /restore — sab data import ho jayega."""
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi /restore use kar sakte hain.")
        return
    msg = update.effective_message
    if not msg.reply_to_message or not msg.reply_to_message.document:
        await msg.reply_text("Backup JSON file pe reply karke /restore bhejo.")
        return
    doc = msg.reply_to_message.document
    if doc.file_size > 5 * 1024 * 1024:
        await msg.reply_text("File 5MB se badi hai — backup itna bada nahi hota.")
        return
    tg_file = await doc.get_file()
    buf = io.BytesIO()
    await tg_file.download_to_memory(buf)
    buf.seek(0)
    try:
        data = json.loads(buf.read().decode())
    except json.JSONDecodeError:
        await msg.reply_text("❌ Valid JSON nahi hai ye file.")
        return
    chat = update.effective_chat
    count = db.import_group_data(chat.id, data)
    await msg.reply_text(f"✅ Restore complete — {count} documents import ho gaye.")
