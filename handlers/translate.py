"""/tr <lang> — kisi message pe reply karke translate. Free deep-translator, no API key."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def cmd_tr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    r = msg.reply_to_message
    if not r or not (r.text or r.caption):
        await msg.reply_text("Kisi message pe reply karke /tr <lang> bhejo. Jaise: /tr en")
        return
    lang = context.args[0].lower() if context.args else "en"
    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source="auto", target=lang).translate(r.text or r.caption)
        await msg.reply_text(
            f"🌐 **{lang}** me translated:\n\n{translated}"
        )
    except ValueError:
        await msg.reply_text("❌ Invalid language code. Examples: en, hi, ur, ar, es, fr")
    except Exception as e:
        logger.warning("Translate fail: %s", e)
        await msg.reply_text("❌ Translate nahi ho paya, thodi der baad try karo.")
