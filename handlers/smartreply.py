"""handlers/smartreply.py — Smart Auto-Reply + Pro Security Mode

/smart hii+hello+halo | Hello there, how can I help you?  → koi bhi word mile to reply
/unsmart <keyword>      → hatao
/smartlist              → sab dekho
/pro on | /pro off      → saari security ek hi command me ON/OFF
"""

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin

logger = logging.getLogger(__name__)

# Naya collection — smart replies (restart-proof, MongoDB me)
_smart_col = db.stats_col.database["smart_replies"]


# ================================================================
# /smart — multi-keyword auto-reply (Rose bot style)
# ================================================================

async def cmd_smart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return

    raw = update.effective_message.text.partition(" ")[2]
    if "|" not in raw:
        await update.message.reply_text(
            "🤖 <b>SMART AUTO-REPLY</b>\n\n"
            "📌 Format: /smart <words with +> | <reply text>\n\n"
            "✨ Examples:\n"
            "• /smart hii+hello+halo | Hello there, how can I help you? 😊\n"
            "• /smart thanks+thankyou | You're welcome bro! 🤝\n"
            "• /smart bye+goodnight | Bye bhai, take care! 👋\n\n"
            "⚡ Koi bhi EK word match hua → bot turant reply karega.\n"
            "🗑️ Hatane ke liye: /unsmart <word>  •  List: /smartlist",
            parse_mode="HTML",
        )
        return

    trigger_part, _, response = raw.partition("|")
    keywords = [w.strip().lower() for w in trigger_part.split("+") if w.strip()]
    response = response.strip()

    if not keywords or not response:
        await update.message.reply_text("❌ Keywords aur reply dono chahiye. Upar format dekho!")
        return
    if len(keywords) > 15:
        await update.message.reply_text("😅 Max 15 keywords ek smart reply me.")
        return

    _smart_col.update_one(
        {"chat_id": update.effective_chat.id, "keywords": keywords},
        {"$set": {"keywords": keywords, "response": response}},
        upsert=True,
    )
    await update.message.reply_text(
        f"✅ <b>Smart reply set!</b>\n\n"
        f"🔑 Keywords: <code>{' + '.join(keywords)}</code>\n"
        f"💬 Reply: <i>{response}</i>",
        parse_mode="HTML",
    )


async def cmd_unsmart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args:
        await update.message.reply_text("Use karo: /unsmart <keyword>")
        return
    word = context.args[0].lower()
    result = _smart_col.delete_one({
        "chat_id": update.effective_chat.id,
        "keywords": word,   # array me match → delete
    })
    if result.deleted_count:
        await update.message.reply_text(f"🗑️ '{word}' wala smart reply hata diya.")
    else:
        await update.message.reply_text(f"🤔 '{word}' kisi smart reply me nahi mila.")


async def cmd_smartlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    docs = list(_smart_col.find({"chat_id": update.effective_chat.id}))
    if not docs:
        await update.message.reply_text(
            "🤖 Is group me koi smart replies nahi.\n"
            "Banao: /smart hii+hello+halo | Hello there, how can I help you?"
        )
        return
    lines = ["🤖 <b>SMART REPLIES:</b>\n"]
    for d in docs:
        lines.append(f"🔑 <code>{' + '.join(d['keywords'])}</code>\n   💬 <i>{d['response']}</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


def _keyword_hit(text_lower: str, keyword: str) -> bool:
    """Word-boundary match — 'hi' sirf 'hi' ya 'Hi!' pe chalega, 'this' pe nahi."""
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return re.search(pattern, text_lower) is not None


async def check_smart_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Har group text message pe chalta hai — koi keyword mile to turant reply."""
    msg = update.effective_message
    chat = update.effective_chat
    if not msg or not msg.text or chat.type not in ("group", "supergroup"):
        return
    if msg.text.startswith("/"):   # commands pe reply mat karo
        return

    text_lower = msg.text.lower()
    for d in _smart_col.find({"chat_id": chat.id}):
        if any(_keyword_hit(text_lower, k) for k in d["keywords"]):
            try:
                await msg.reply_text(d["response"])
            except Exception:
                pass
            return   # ek reply per message — spam nahi


# ================================================================
# /pro on|off — saari security ek command me
# ================================================================

def _set_quarantine(chat_id, value: bool):
    # wahi settings key jo security.py + settings_panel.py use karte hain
    db.settings_col.update_one(
        {"chat_id": chat_id}, {"$set": {"quarantine": value}}, upsert=True
    )


async def cmd_pro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.message.reply_text(
            "🛡️ <b>PRO SECURITY MODE</b>\n\n"
            "📌 Use karo: /pro on  ya  /pro off\n\n"
            "/pro <b>on</b> karne se ye sab ek saath ON ho jayega:\n"
            "🛡️ Raid protection (auto-lock on mass joins)\n"
            "🔗 Link/username blocker (warns + auto-ban)\n"
            "🚫 Anti-forward (forwarded messages delete)\n"
            "🧊 Quarantine (sus members ko isolate)\n\n"
            "ℹ️ Flood anti-spam hamesha active rehta hai (built-in).\n"
            "ℹ️ /pro <b>off</b> in sab ko OFF kar dega — group khul jayega.",
            parse_mode="HTML",
        )
        return

    chat_id = update.effective_chat.id
    on = context.args[0].lower() == "on"

    try:
        db.set_raid_protection(chat_id, on)      # 🛡️ raid auto-lock
        db.set_link_block(chat_id, on)           # 🔗 link/scam blocker
        db.set_antiforward(chat_id, on)          # 🚫 anti-forward
        _set_quarantine(chat_id, on)             # 🧊 quarantine
    except Exception as e:
        logger.warning("pro toggle fail %s: %s", chat_id, e)
        await update.message.reply_text("❌ Kuch settings change nahi hui — dobara try karo.")
        return

    state = "ON ✅" if on else "OFF ❌"
    emoji = "🛡️" if on else "🔓"
    await update.message.reply_text(
        f"{emoji} <b>PRO SECURITY MODE: {state}</b>\n\n"
        f"🛡️ Raid protection: {state}\n"
        f"🔗 Link blocker: {state}\n"
        f"🚫 Anti-forward: {state}\n"
        f"🧊 Quarantine: {state}\n\n"
        f"{'🕵️ Ab group tight security me hai — raid aaye to auto-lock hoga!' if on else '😐 Security loose ho gayi — sirf flood control chal raha hai.'}",
        parse_mode="HTML",
    )
