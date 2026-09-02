"""Inline-button control panel shown from /start:

  ➕ Add me to your group
  👥 My Groups        ⚙️ Group Settings
  👑 Owner Panel

- "Group Settings" opens the new 3-layer settings panel (settings_panel.py).
- "My Groups" shows groups where the user is admin + bot is present.
- "Owner Panel" is restricted to OWNER_IDS.

All of this is driven entirely by callback_query buttons so it works fully
inside a private chat with the bot.
"""

import html
import logging
from collections import deque

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import database as db
from config import BOT_NAME, BOT_CREDIT, OWNER_IDS, OFFICIAL_CHANNEL_URL

GROUPS_PER_PAGE = 8
LOG_LINES_SHOWN = 30
LOG_BUFFER_SIZE = 300
MAX_MESSAGE_CHARS = 3500 

# key -> (label, emoji, getter, setter)
TOGGLES = {
    "link_block": ("Link/Username Block", "🔗", db.get_link_block, db.set_link_block),
    "night_mode": ("Night Mode", "🌙", db.get_night_mode, db.set_night_mode),
    "raid_protection": ("Raid Protection", "🛡️", db.get_raid_protection, db.set_raid_protection),
    "rules_gate": ("Rules-Accept Gate", "📜", db.get_rules_gate, db.set_rules_gate),
    "autopin": ("Auto-Pin", "📌", db.get_autopin, db.set_autopin),
    "autodelete_joinleave": ("Auto-Delete Join/Leave", "🧹", db.get_autodelete_joinleave, db.set_autodelete_joinleave),
}


# ---------------- In-memory log capture (for Owner Panel: Live Logs / Errors) ----------------

_all_logs: deque = deque(maxlen=LOG_BUFFER_SIZE)
_error_logs: deque = deque(maxlen=LOG_BUFFER_SIZE)


class PanelLogHandler(logging.Handler):
    """A logging.Handler that just stores formatted records in memory."""

    def emit(self, record):
        try:
            line = self.format(record)
        except Exception:
            return
        _all_logs.append(line)
        if record.levelno >= logging.WARNING:
            _error_logs.append(line)

log_handler = PanelLogHandler()
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))


def _is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


async def _safe_edit(query, text: str, kb: InlineKeyboardMarkup):
    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    except BadRequest as e:
        if "not modified" in str(e).lower():
            return
        # Message too old / can't edit — new bhej do
        try:
            await query.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass


# ---------------- Home screen ----------------

def home_text() -> str:
    return (
    f"🤖 <b>Welcome to {html.escape(BOT_NAME)}!</b>\n"
    "<i>Group Management, Simplified.</i>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "Aapke Telegram groups ko safe, active aur engaging rakhne ka all-in-one solution. ⚡\n\n"
    "🛡️ <b>Key Features:</b>\n"
    " ├ 🛑 <b>Anti-Spam & Raid Protection</b>\n"
    " ├ ⚙️ <b>Advanced Filters & Custom Notes</b>\n"
    " ├ 📈 <b>XP System & Leaderboards</b>\n"
    " └ 📊 <b>Polls, Mini-Games & Utility Tools</b>\n\n"
    "✅ Sab kuch ek jagah, bilkul FREE!\n\n"
    "👇 Neeche diye gaye buttons se option chuno:\n\n"
    "📢 <b>Updates:</b> @theteamvb\n"
    "🌟 <b>Made with ❤️ TEAMVB</b>"
)


def start_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Mujhe Group Me Add Karo",
                              url=f"https://t.me/{bot_username}?startgroup=true")],
        [
            InlineKeyboardButton("👥 My Groups", callback_data="pnl:mygroups"),
            InlineKeyboardButton("⚙️ Group Settings", callback_data="setpnl:start"),
        ],
        [InlineKeyboardButton("👑 Owner Panel", callback_data="pnl:owner")],
        [InlineKeyboardButton("📢 Official Channel", url=OFFICIAL_CHANNEL_URL)],
    ])


async def _send_home(query, context):
    try:
        bot_username = (await context.bot.get_me()).username
    except Exception:
        bot_username = ""
    await _safe_edit(query, home_text(), start_keyboard(bot_username))


# ---------------- My Groups + old flat settings (compatibility) ----------------

async def _admin_groups_for(context, user_id):
    mine = []
    for g in db.get_all_groups()[:50]:
        try:
            m = await context.bot.get_chat_member(g["chat_id"], user_id)
            if m.status in ("administrator", "creator"):
                mine.append(g)
        except Exception:
            continue
    return mine


async def show_my_groups(update, context, page: int = 0):
    query = update.callback_query
    if not await _is_group_admin(context, query.from_user.id):
        return
    mine = await _admin_groups_for(context, query.from_user.id)
    if not mine:
        await _safe_edit(
            query,
            "😅 <b>Arre yaar...</b>\n\nKoi aisa group nahi mila jahan tum admin ho aur main bhi hoon. "
            "Pehle mujhe group me add karo aur admin banao — main yahin intezaar karunga, coffee ke saath. ☕🤖",
            InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Wapas", callback_data="pnl:home")]]),
        )
        return
    start = page * GROUPS_PER_PAGE
    chunk = mine[start:start + GROUPS_PER_PAGE]
    kb = [[InlineKeyboardButton(f"👥 {html.escape(g['title'][:28])}", callback_data=f"pnl:group:{g['chat_id']}")]
          for g in chunk]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Peeche", callback_data=f"pnl:mygroups:{page - 1}"))
    if start + GROUPS_PER_PAGE < len(mine):
        nav.append(InlineKeyboardButton("Aage ➡️", callback_data=f"pnl:mygroups:{page + 1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🔙 Wapas", callback_data="pnl:home")])
    await _safe_edit(
        query,
        f"👥 <b>Tumhare groups</b> ({len(mine)})\n\nEk chuno — settings dikhata hoon. 😊",
        InlineKeyboardMarkup(kb),
    )


async def _is_group_admin(context, user_id: int) -> bool:
    if _is_owner(user_id):
        return True
    try:
        return True  # mygroups screen khud filter karti hai
    except Exception:
        return False


async def show_group_settings(update, context, chat_id: int):
    """Old flat toggle panel — ab bhi 'My Groups' se accessible (compatibility)."""
    query = update.callback_query
    kb = []
    for key, (label, emoji, getter, _setter) in TOGGLES.items():
        try:
            state = bool(getter(chat_id))
        except Exception:
            state = False
        kb.append([InlineKeyboardButton(
            f"{emoji} {label}: {'✅ ON' if state else '❌ OFF'}",
            callback_data=f"pnl:toggle:{chat_id}:{key}",
        )])
    kb.append([InlineKeyboardButton("🗂️ Naya 3-Layer Panel", callback_data="setpnl:start")])
    kb.append([InlineKeyboardButton("🔙 Wapas", callback_data="pnl:mygroups")])
    await _safe_edit(
        query,
        "⚙️ <b>Group Settings (purana panel)</b>\n\n"
        "Naya 3-layer panel bhi hai — Basic/Medium/Advanced, hints ke saath. "
        "Neeche 'Naya 3-Layer Panel' dabao. 🤗",
        InlineKeyboardMarkup(kb),
    )


async def toggle_group_setting(update, context, chat_id: int, key: str):
    query = update.callback_query
    if key not in TOGGLES:
        await query.answer("Setting nahi mili 🤔", show_alert=True)
        return
    label, emoji, getter, setter = TOGGLES[key]
    try:
        new_val = not bool(getter(chat_id))
        setter(chat_id, new_val)
    except Exception:
        await query.answer("❌ Nahi hua — dobara try karo", show_alert=True)
        return
    await query.answer(f"{emoji} {label}: {'✅ ON' if new_val else '❌ OFF'}")
    await show_group_settings(update, context, chat_id)


# ---------------- Owner Panel ----------------

def _fmt_num(n: int) -> str:
    return f"{n:,}"


async def show_owner_panel(update, context):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Stats", callback_data="pnl:ostats"),
         InlineKeyboardButton("📢 Broadcast", callback_data="pnl:obroadcast")],
        [InlineKeyboardButton("👥 Groups", callback_data="pnl:ogroups")],
        [InlineKeyboardButton("🧾 Live Logs", callback_data="pnl:ologs"),
         InlineKeyboardButton("🐞 Errors", callback_data="pnl:oerrors")],
        [InlineKeyboardButton("🔙 Home", callback_data="pnl:home")],
    ])
    await _safe_edit(
        query,
        "👑 <b>Owner Panel</b>\n\nBoss aa gaye! 😎 Sab kuch yahin control me — "
        "stats dekho, sabko message bhejo, logs me jhaanko.\n\n"
        "<i>Aap aaram se baitho, group ki chowkidaari meri zimmedari.</i> 💪",
        kb,
    )


async def show_owner_stats(update, context):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return
    s = db.get_bot_wide_stats()
    text = (
        "📊 <b>Bot-Wide Stats</b>\n\n"
        f"👥 Groups: <b>{_fmt_num(s['groups'])}</b>\n"
        "🧑‍🤝‍🧑 Users: <b>" + _fmt_num(s['users']) + "</b>\n"
        "💬 Messages: <b>" + _fmt_num(s['messages']) + "</b>\n"
        "⚡ Commands: <b>" + _fmt_num(s['commands']) + "</b>"
    )
    await _safe_edit(query, text, InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 Owner Panel", callback_data="pnl:owner")]]
    ))


async def show_owner_groups(update, context, page: int = 0):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return
    groups = db.get_all_groups()
    start = page * GROUPS_PER_PAGE
    chunk = groups[start:start + GROUPS_PER_PAGE]
    kb = [[InlineKeyboardButton(
        f"👥 {html.escape(g['title'][:24])} — 🚪 Leave",
        callback_data=f"pnl:leave:{g['chat_id']}",
    )] for g in chunk]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Peeche", callback_data=f"pnl:ogroups:{page - 1}"))
    if start + GROUPS_PER_PAGE < len(groups):
        nav.append(InlineKeyboardButton("Aage ➡️", callback_data=f"pnl:ogroups:{page + 1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("🔙 Owner Panel", callback_data="pnl:owner")])
    await _safe_edit(
        query,
        f"👥 <b>Saare groups</b> ({len(groups)}) — leave button ke saath",
        InlineKeyboardMarkup(kb),
    )


async def leave_group(update, context, chat_id: int):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return
    try:
        await context.bot.leave_chat(chat_id)
    except Exception:
        pass
    db.remove_group(chat_id)
    await query.answer("Group leave kar diya.")
    await show_owner_groups(update, context, page=0)




def _format_log_block(lines, empty_msg: str) -> str:
    """Last N log lines, but never exceed Telegram's message limit."""
    if not lines:
        return f"<i>{empty_msg}</i>"
    result_lines = []
    total = 0
    for line in reversed(lines):  # nayi lines pehle uthao
        size = len(html.escape(line)) + 1
        if total + size > MAX_MESSAGE_CHARS:
            break
        result_lines.append(line)
        total += size
    if not result_lines:
        result_lines = [html.escape(lines[-1])[:MAX_MESSAGE_CHARS - 20] + " …"]
    result_lines.reverse()
    return "<code>" + "\n".join(result_lines) + "</code>"


async def show_owner_logs(update, context):
  await query.answer()
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return

    body = _format_log_block(list(_all_logs), "Abhi tak koi log capture nahi hua.")
    text = (
        f"🧾 <b>Live Logs</b> <i>(last {min(len(_all_logs), LOG_LINES_SHOWN)})</i>\n"
        "<i>Ye history hai — jab tak clear ya restart na ho, purani lines yahin rahengi.</i>\n\n"
        f"{body}"
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="pnl:ologs"),
                InlineKeyboardButton("🗑 Clear", callback_data="pnl:oclearlogs"),
            ],
            [InlineKeyboardButton("🔙 Owner Panel", callback_data="pnl:owner")],
        ]
    )
    await _edit_or_alert(query, text, kb)

async def show_owner_errors(update, context):
  await query.answer()
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return

    body = _format_log_block(list(_error_logs), "Koi error record nahi hai — sab sahi chal raha hai ✅")
    text = (
        f"🐞 <b>Errors</b> <i>(last {min(len(_error_logs), LOG_LINES_SHOWN)})</i>\n"
        "<i>Ye bhi history hai — ek purani error yahan tab tak dikhti rahegi jab tak clear na karo, "
        "chahe wo ab dobara na ho rahi ho.</i>\n\n"
        f"{body}"
    )
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Refresh", callback_data="pnl:oerrors"),
                InlineKeyboardButton("🗑 Clear", callback_data="pnl:oclearerrors"),
            ],
            [InlineKeyboardButton("🔙 Owner Panel", callback_data="pnl:owner")],
        ]
    )
    await _edit_or_alert(query, text, kb)


async def clear_owner_logs(update, context):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return
    _all_logs.clear()
    await query.answer("Logs clear kar diye ✅")
    await show_owner_logs(update, context)


async def clear_owner_errors(update, context):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return
    _error_logs.clear()
    await query.answer("Errors clear kar diye ✅")
    await show_owner_errors(update, context)


async def start_broadcast(update, context):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return

    context.user_data["awaiting_broadcast"] = True
    await query.edit_message_text(
        "📢 <b>Broadcast</b>\n\nAgla message jo tum yahan bhejoge, wo sab groups me bhej diya jayega.\n"
        "Cancel karne ke liye /cancel bhejo.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Owner Panel", callback_data="pnl:owner")]]),
    )


async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Called from bot.py's private-chat text handler. Returns True if this
    message was consumed as a broadcast (so the caller shouldn't do anything
    else with it)."""
    if not context.user_data.get("awaiting_broadcast"):
        return False

    context.user_data["awaiting_broadcast"] = False
    user_id = update.effective_user.id
    if not _is_owner(user_id):
        return False

    if update.effective_message.text and update.effective_message.text.strip() == "/cancel":
        await update.effective_message.reply_text("❌ Broadcast cancel kar diya.")
        return True

    groups = db.get_all_groups()
    sent, failed = 0, 0
    for g in groups:
        try:
            await context.bot.copy_message(
                chat_id=g["chat_id"],
                from_chat_id=update.effective_chat.id,
                message_id=update.effective_message.message_id,
            )
            sent += 1
        except Exception:
            failed += 1

    await update.effective_message.reply_text(
        f"📢 Broadcast bhej diya.\n✅ Sent: {sent}\n❌ Failed: {failed}"
    )
    return True
  

async def _edit_or_alert(query, text, kb):
    """Edit karo; agar content same hai to chup raho, warna user ko error dikhao.
    Ab kabhi bhi button 'dead' nahi lagega — hamesha kuch response milega."""
    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            try:
                await query.answer(f"⚠️ {str(e)[:180]}", show_alert=True)
            except Exception:
                pass
    except Exception as e:
        try:
            await query.answer(f"⚠️ {str(e)[:180]}", show_alert=True)
        except Exception:
            pass


# ---------------- Callback router ----------------

async def on_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""
    parts = data.split(":")

    action = parts[1] if len(parts) > 1 else ""

    if action == "home":
        await _send_home(query, context)
    elif action == "mygroups":
        page = int(parts[2]) if len(parts) > 2 else 0
        await show_my_groups(update, context, page)
    elif action == "group":
        await show_group_settings(update, context, int(parts[2]))
    elif action == "toggle":
        await toggle_group_setting(update, context, int(parts[2]), parts[3])
    elif action == "owner":
        await show_owner_panel(update, context)
    elif action == "ostats":
        await show_owner_stats(update, context)
    elif action == "obroadcast":
        await start_broadcast(update, context)
    elif action == "ogroups":
        page = int(parts[2]) if len(parts) > 2 else 0
        await show_owner_groups(update, context, page)
    elif action == "leave":
        await leave_group(update, context, int(parts[2]))
    elif action == "ologs":
        await show_owner_logs(update, context)
    elif action == "oerrors":
        await show_owner_errors(update, context)
    elif action == "oclearlogs":
        await clear_owner_logs(update, context)
    elif action == "oclearerrors":
        await clear_owner_errors(update, context)
    elif action == "noop":
        await query.answer()
    else:
        await query.answer()
