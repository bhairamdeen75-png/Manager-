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

# MyMemory free tier ka hard limit — isse zyada bhejne par woh translation
# ki jagah apna khud ka error-text return kar deta hai (jo exception nahi
# hai, isliye pehle isko detect na karna galat "translation" dikha raha tha)
MYMEMORY_CHAR_LIMIT = 500

_ERROR_MARKERS = (
    "error 500", "mymemory warning", "is an invalid target language",
    "query length limit", "amount of words limit", "please try again later",
)


def _looks_like_error(text: str) -> bool:
    low = text.lower()
    return any(marker in low for marker in _ERROR_MARKERS)


async def cmd_tr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    r = msg.reply_to_message
    if not r or not (r.text or r.caption):
        await msg.reply_text("Kisi message pe reply karke /tr <lang> bhejo. Jaise: /tr en")
        return
    lang = context.args[0].lower() if context.args else "en"
    text = r.text or r.caption

    # Telegram/Google donon ke liye ek sensible cap — bahut lambe messages
    # (jaise /wiki extract) translate karne me practical nahi, isliye
    # truncate karke bata do
    MAX_TRANSLATE_CHARS = 3000
    truncated = False
    if len(text) > MAX_TRANSLATE_CHARS:
        text = text[:MAX_TRANSLATE_CHARS]
        truncated = True

    translated = None

    # 1st try: MyMemory — SIRF tab jab text uski 500-char limit ke andar ho
    if len(text) <= MYMEMORY_CHAR_LIMIT:
        try:
            from deep_translator import MyMemoryTranslator
            t_lang = LANG_MAP.get(lang, lang)
            result = MyMemoryTranslator(
                source="auto" if hasattr(MyMemoryTranslator, "_AUTO") else "english",
                target=t_lang,
            ).translate(text)
            if result and not _looks_like_error(result):
                translated = result
            else:
                logger.warning("MyMemory returned error-text, falling back to Google")
        except ValueError:
            await msg.reply_text("❌ Invalid language code. Examples: en, hi, ur, ar, es, fr")
            return
        except Exception as e:
            logger.warning("MyMemory fail: %s", e)

    # 2nd try: Google fallback — lambe text ke liye bhi ye hi chalega,
    # aur agar MyMemory ne error-text diya ho tab bhi
    if not translated:
        try:
            from deep_translator import GoogleTranslator
            g_lang = LANG_MAP.get(lang, lang)
            result = GoogleTranslator(source="auto", target=g_lang).translate(text)
            if result and not _looks_like_error(result):
                translated = result
        except Exception as e:
            logger.warning("Google translate fail: %s", e)

    if translated:
        note = "\n\n<i>(lamba text tha, shuru ka hissa translate kiya)</i>" if truncated else ""
        await msg.reply_text(f"🌐 <b>{lang}</b> me translated:\n\n{translated}{note}", parse_mode="HTML")
    else:
        await msg.reply_text("❌ Translate nahi ho paya, thodi der baad try karo.")
