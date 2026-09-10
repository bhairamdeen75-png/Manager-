import httpx
from telegram import Update
from telegram.ext import ContextTypes

from config import DICTIONARY_API_URL


async def cmd_define(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/define <word> — free dictionaryapi.dev, no key required."""
    if not context.args:
        await update.message.reply_text("Use karo: /define <word>")
        return
    word = context.args[0].lower()

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(DICTIONARY_API_URL.format(word=word))
    except Exception:
        await update.message.reply_text("❌ Dictionary service abhi reach nahi ho pa raha, thodi der me try karo.")
        return

    if resp.status_code != 200:
        await update.message.reply_text(f"'{word}' ka meaning nahi mila.")
        return

    try:
        data = resp.json()[0]
    except Exception:
        await update.message.reply_text(f"'{word}' ka meaning nahi mila.")
        return

    lines = [f"📖 <b>{data.get('word', word)}</b>"]
    phonetic = data.get("phonetic") or ""
    if phonetic:
        lines.append(f"<i>{phonetic}</i>")

    for meaning in data.get("meanings", [])[:3]:
        pos = meaning.get("partOfSpeech", "")
        lines.append(f"\n<b>{pos}</b>")
        for defn in meaning.get("definitions", [])[:2]:
            lines.append(f"• {defn.get('definition', '')}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
