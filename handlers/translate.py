# handlers/translate.py
"""handlers/translate.py — /tr command, stable free translation."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

LANG_MAP = {
    "en": "english", "hi": "hindi", "ur": "urdu", "ar": "arabic",
    "es": "spanish", "fr": "french", "de": "german", "ru": "russian",
    "pt": "portuguese", "bn": "bengali", "ta": "tamil", "zh-CN": "chinese (simplified)",
}


async def cmd_tr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    r = msg.reply_to_message
    if not r or not (r.text or r.caption):
        await msg.reply_text("Kisi message pe reply karke /tr <lang> bhejo. Jaise: /tr en")
        return
    lang = context.args[0].lower() if context.args else "en"
    text = r.text or r.caption

    translated = None
    # 1st try: MyMemory (stable, free, no key)
    try:
        from deep_translator import MyMemoryTranslator
        t_lang = LANG_MAP.get(lang, lang)
        translated = MyMemoryTranslator(source="auto" if hasattr(MyMemoryTranslator, "_AUTO") else "english", target=t_lang).translate(text)
    except ValueError:
        await msg.reply_text("❌ Invalid language code. Examples: en, hi, ur, ar, es, fr")
        return
    except Exception as e:
        logger.warning("MyMemory fail: %s", e)

    # 2nd try: Google fallback (agar MyMemory me language na mili ho)
    if not translated:
        try:
            from deep_translator import GoogleTranslator
            translated = GoogleTranslator(source="auto", target=lang).translate(text)
        except Exception as e:
            logger.warning("Google translate fail: %s", e)

    if translated:
        await msg.reply_text(f"🌐 **{lang}** me translated:\n\n{translated}")
    else:
        await msg.reply_text("❌ Translate nahi ho paya, thodi der baad try karo.")
