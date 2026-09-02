"""Settings Panel 2.0 — DM me bot ko /start karke ⚙️ Group Settings dabao.

Teeno layers (Basic/Medium/Advanced) me sirf ON/OFF wali settings hain.
Baaki sab settings group me commands se hoti hain (/sethelp dekho).
Har layer ka apna pyaara hint message bhi hai. 💛
"""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

import database as db
from config import OWNER_IDS

logger = logging.getLogger(__name__)


def _is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


# ---- Quarantine helpers (security.py wale hi keys use karta hai — compatible) ----

def _get_quarantine(chat_id) -> bool:
    doc = db.settings_col.find_one({"chat_id": chat_id})
    return doc.get("quarantine", False) if doc else False


def _set_quarantine(chat_id, value: bool):
    db.settings_col.update_one({"chat_id": chat_id}, {"$set": {"quarantine": value}}, upsert=True)


# ---------------- Layers (sirf ON/OFF settings) ----------------

LAYERS = {
    "basic": {
        "title": "🟢 Basic Settings",
        "message": (
            "🌱 <b>Chalo shuru karte hain sabse pyaari layer se!</b>\n\n"
            "Ye wo settings hain jo tumhe sabse zyada kaam aayengi — bilkul simple, "
            "bas button dabao aur ho gaya. Na sochna padega, na tension lena padega. 🤗\n\n"
            "Tum masti karo, main group ki chowkidaari karta hoon. "
            "Roz ki dekhbhal meri zimmedari, aaram tumhara. 💪✨"
        ),
        "hint": (
            "💡 <b>Basic Settings ki hint:</b>\n\n"
            "🌙 <b>Night Mode</b> — raat me group sota hai, subah bot khud handle karega.\n"
            "🧹 <b>Auto-Delete Join/Leave</b> — 'XYZ joined the group' wale faltu messages udd jayenge.\n"
            "📌 <b>Auto-Pin</b> — admin ka har message khud pin ho jayega.\n\n"
            "🤖 <b>Baaki commands (group me):</b>\n"
            "/setwelcome • /setleave • /setrules • /rules • /remindme • /rank • /leaderboard"
        ),
        "toggles": {
            "night_mode": ("Night Mode", "🌙", db.get_night_mode, db.set_night_mode),
            "autodelete_joinleave": ("Auto-Delete Join/Leave", "🧹", db.get_autodelete_joinleave, db.set_autodelete_joinleave),
            "autopin": ("Auto-Pin", "📌", db.get_autopin, db.set_autopin),
        },
    },
    "medium": {
        "title": "🟡 Medium Settings",
        "message": (
            "🟡 <b>Waah, thoda level up kar rahe ho!</b>\n\n"
            "Ye layer un groups ke liye hai jo thoda strict rakhna chahte hain — "
            "links pe nazar, rules ka gate, forwarded spam ka thehrao. 😤\n\n"
            "Tum chinta mat karo — jab tum so rahe hote ho, tab bhi main jaag raha hota hoon. "
            "Har link, har forward, har shaitani pe meri nazar hai. "
            "Tum bas family sambhalo, border main sambhalunga. 🛡️❤️"
        ),
        "hint": (
            "💡 <b>Medium Settings ki hint:</b>\n\n"
            "🔗 <b>Link Block</b> — links/usernames wale messages delete (admins exempt).\n"
            "📜 <b>Rules Gate</b> — naya member pehle rules accept kare, tab bol payega.\n"
            "🚫 <b>Anti-Forward</b> — dusre chat se forward kiya hua message delete.\n\n"
            "🤖 <b>Baaki commands (group me):</b>\n"
            "/addfilter • /filters • /allowdomain • /antiforward • /setlinkblock • /rulesgate"
        ),
        "toggles": {
            "link_block": ("Link/Username Block", "🔗", db.get_link_block, db.set_link_block),
            "rules_gate": ("Rules-Accept Gate", "📜", db.get_rules_gate, db.set_rules_gate),
            "antiforward": ("Anti-Forward", "🚫", db.get_antiforward, db.set_antiforward),
        },
    },
    "advanced": {
        "title": "🔴 Advanced Settings",
        "message": (
            "🔴 <b>Arre waah — pro player aa gaya! 😎</b>\n\n"
            "Ye layer sirf unke liye hai jo apne group ko kila bana na chahte hain. "
            "Raid aaye to darwaze band, shak wale naye members quarantine me, "
            "aur spammer ki ek galti — seedha bahar. ⚔️\n\n"
            "Sach kahoon? Itne tight security wale group maine kam dekhe hain. "
            "Tumhare group me ghusna aasan nahi hai ab — "
            "aur ye meri sabse pyaari izzat hai. 🫡✨"
        ),
        "hint": (
            "💡 <b>Advanced Settings ki hint:</b>\n\n"
            "🛡️ <b>Raid Protection</b> — bhari bhadak joins aaye to auto-lock + captcha.\n"
            "🧊 <b>Quarantine</b> — naye members 24h sirf text bhej sakein (no links/media/files).\n\n"
            "🤖 <b>Baaki commands (group me):</b>\n"
            "/setraidlimits • /setcaptchamode • /lock • /unlock • /checkperms • /securitystatus • /quarantine"
        ),
        "toggles": {
            "raid_protection": ("Raid Protection", "🛡️", db.get_raid_protection, db.set_raid_protection),
            "quarantine": ("Quarantine (24h new members)", "🧊", _get_quarantine, _set_quarantine),
        },
    },
}

LAYER_EMOJI = {"basic": "🟢", "medium": "🟡", "advanced": "🔴"}


# ---------------- Helpers ----------------

async def _is_group_admin(context, chat_id, user_id) -> bool:
    if _is_owner(user_id):
        return True
    try:
        m = await context.bot.get_chat_member(chat_id, user_id)
        return m.status in ("administrator", "creator")
    except Exception:
        return False


def _state(gid, getter) -> bool:
    try:
        return bool(getter(gid))
    except Exception:
        return False


# ---------------- Screens ----------------

async def show_group_picker(update, context):
    query = update.callback_query
    groups = db.get_all_groups()
    # Sirf wo groups jahan ye user admin hai
    mine = []
    for g in groups[:25]:
        if await _is_group_admin(context, g["chat_id"], query.from_user.id):
            mine.append(g)
    if not mine:
        await query.edit_message_text(
            "😅 <b>Arre yaar...</b>\n\n"
            "Mujhe koi aisa group nahi mila jahan tum admin ho aur main bhi hoon. "
            "Pehle mujhe group me add karo aur admin banao, phir yahan aana. "
            "Main yahin intezaar karunga — coffee ke saath. ☕🤖",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Wapas", callback_data="pnl:home")]]
            ),
        )
        return
    kb = [[InlineKeyboardButton(f"👥 {g['title'][:28]}", callback_data=f"setpnl:g:{g['chat_id']}")]
          for g in mine]
    kb.append([InlineKeyboardButton("🔙 Wapas", callback_data="pnl:home")])
    await query.edit_message_text(
        "⚙️ <b>Group Settings</b>\n\n"
        "Kis group ki baat karein, boss? 😊\n"
        "<i>Ye wo groups hain jahan tum admin ho aur main bhi khada hoon — "
        "ek chunta hua bodyguard. 😄</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def show_layers(update, context, chat_id: int):
    query = update.callback_query
    kb = [
        [InlineKeyboardButton("🟢 Basic", callback_data=f"setpnl:l:{chat_id}:basic")],
        [InlineKeyboardButton("🟡 Medium", callback_data=f"setpnl:l:{chat_id}:medium")],
        [InlineKeyboardButton("🔴 Advanced", callback_data=f"setpnl:l:{chat_id}:advanced")],
        [InlineKeyboardButton("🔙 Doosra group", callback_data="setpnl:start")],
    ]
    await query.edit_message_text(
        "🗂️ <b>Teen layers — teen level ki taakat!</b>\n\n"
        "🟢 <b>Basic</b> — roz ki settings, sabse pyaari.\n"
        "🟡 <b>Medium</b> — thodi strict nazar, links aur rules pe.\n"
        "🔴 <b>Advanced</b> — full kila mode, raids ka jawab.\n\n"
        "Har layer me sirf ON/OFF buttons hain — confusion zero, control full. "
        "Hint button dabao to main sab pyaare pyaare samjha dunga. 🤗",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def show_layer(update, context, chat_id: int, layer_key: str):
    layer = LAYERS[layer_key]
    kb = []
    for key, (label, emoji, getter, _setter) in layer["toggles"].items():
        state = _state(chat_id, getter)
        btn = f"{emoji} {label}: {'✅ ON' if state else '❌ OFF'}"
        kb.append([InlineKeyboardButton(btn, callback_data=f"setpnl:t:{chat_id}:{layer_key}:{key}")])
    kb.append([InlineKeyboardButton("❓ Hint/Help", callback_data=f"setpnl:h:{layer_key}")])
    kb.append([InlineKeyboardButton("🔙 Layers", callback_data=f"setpnl:g:{chat_id}")])
    await query_edit_layer(update, layer, chat_id, kb)


async def query_edit_layer(update, layer, chat_id, kb):
    query = update.callback_query
    await query.edit_message_text(
        f"<b>{layer['title']}</b>\n\n{layer['message']}\n\n"
        "👇 <i>Button dabao — turant ON/OFF ho jayega.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def show_hint(update, context, layer_key: str):
    query = update.callback_query
    layer = LAYERS[layer_key]
    kb = [[InlineKeyboardButton("🔙 Wapas", callback_data="setpnl:back")]]
    await query.edit_message_text(
        layer["hint"] + "\n\n<i>Koi dikkat aaye to group me /checkperms chala lena — "
        "main bata dunga meri kya powers hain. 😄</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )
    # back ke liye layer yaad rakho
    context.user_data["setpnl_last_layer"] = layer_key


async def do_toggle(update, context, chat_id: int, layer_key: str, key: str):
    query = update.callback_query
    layer = LAYERS[layer_key]
    if key not in layer["toggles"]:
        await query.answer("Ye setting nahi mili 🤔", show_alert=True)
        return
    label, emoji, getter, setter = layer["toggles"][key]
    new_val = not _state(chat_id, getter)
    try:
        setter(chat_id, new_val)
    except Exception as e:
        logger.warning("toggle fail %s/%s: %s", chat_id, key, e)
        await query.answer("❌ Nahi hua — dobara try karo", show_alert=True)
        return
    await query.answer(f"{emoji} {label}: {'✅ ON' if new_val else '❌ OFF'}")
    # Refresh layer screen with fresh states
    kb = []
    for k2, (label2, emoji2, getter2, _s2) in layer["toggles"].items():
        st = _state(chat_id, getter2)
        kb.append([InlineKeyboardButton(
            f"{emoji2} {label2}: {'✅ ON' if st else '❌ OFF'}",
            callback_data=f"setpnl:t:{chat_id}:{layer_key}:{k2}",
        )])
    kb.append([InlineKeyboardButton("❓ Hint/Help", callback_data=f"setpnl:h:{layer_key}")])
    kb.append([InlineKeyboardButton("🔙 Layers", callback_data=f"setpnl:g:{chat_id}")])
    await query_edit_layer(update, layer, chat_id, kb)


# ---------------- Router ----------------

async def on_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    parts = data.split(":")

    if parts[1] == "start":
        await show_group_picker(update, context)
    elif parts[1] == "g":
        chat_id = int(parts[2])
        if not await _is_group_admin(context, chat_id, query.from_user.id):
            await query.answer("Ye group ka admin nahi ho tum 😅", show_alert=True)
            return
        await show_layers(update, context, chat_id)
    elif parts[1] == "l":
        chat_id, layer_key = int(parts[2]), parts[3]
        if layer_key not in LAYERS or not await _is_group_admin(context, chat_id, query.from_user.id):
            await query.answer("Allowed nahi hai 😅", show_alert=True)
            return
        await show_layer(update, context, chat_id, layer_key)
    elif parts[1] == "t":
        chat_id, layer_key, key = int(parts[2]), parts[3], parts[4]
        if layer_key not in LAYERS or not await _is_group_admin(context, chat_id, query.from_user.id):
            await query.answer("Allowed nahi hai 😅", show_alert=True)
            return
        await do_toggle(update, context, chat_id, layer_key, key)
    elif parts[1] == "h":
        await show_hint(update, context, parts[2])
    elif parts[1] == "back":
        layer_key = context.user_data.get("setpnl_last_layer", "basic")
        await show_hint_restore(update, context, layer_key)
    else:
        await query.answer()


async def show_hint_restore(update, context, layer_key):
    """Hint se wapas — layer screen dobara dikhao (last chat_id se)."""
    layer = LAYERS.get(layer_key, LAYERS["basic"])
    # chat_id pata nahi to layers picker pe bhej do
    kb = [[InlineKeyboardButton("🔙 Layers", callback_data="setpnl:start")]]
    await update.callback_query.edit_message_text(
        f"<b>{layer['title']}</b>\n\n{layer['message']}",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(kb),
    )


# ---------------- /sethelp command (group + DM dono me) ----------------

SETHelp_TEXT = (
    "💡 <b>Settings ki poori guide — pyaare pyaare</b> 💛\n\n"
    "🟢 <b>Basic</b> — Night Mode 🌙, Auto-Delete Join/Leave 🧹, Auto-Pin 📌\n"
    "🟡 <b>Medium</b> — Link Block 🔗, Rules Gate 📜, Anti-Forward 🚫\n"
    "🔴 <b>Advanced</b> — Raid Protection 🛡️, Quarantine 🧊\n\n"
    "Sab toggles DM me hain: mujhe /start karo → ⚙️ Group Settings.\n\n"
    "🤖 <b>Jo ON/OFF nahi hai, wo commands se (group me):</b>\n"
    "/setwelcome • /setrules • /addfilter • /allowdomain • /setcaptchamode • "
    "/setraidlimits • /setnighttime • /setwmedia • /schedule • /checkperms • /securitystatus"
)


async def cmd_sethelp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(
        "⚙️ Settings Kholo", callback_data="setpnl:start"
    )]]) if update.effective_chat.type == "private" else None
    await update.message.reply_text(SETHelp_TEXT, parse_mode=ParseMode.HTML, reply_markup=kb)
