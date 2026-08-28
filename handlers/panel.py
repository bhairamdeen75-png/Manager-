"""Inline-button control panel shown from /start:

  ➕ Add me to your group
  👥 My Groups        ⚙️ Group Settings
  👑 Owner Panel

- "My Groups" / "Group Settings" both open a picker of groups the requesting
  user administers (where the bot is also present), then a live toggle panel
  for that group's protection settings.
- "Owner Panel" is restricted to OWNER_IDS and gives bot-wide stats, a
  broadcast tool, a group list with a leave option, and live logs/errors
  captured straight from the bot's own logging output.

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
    """A logging.Handler that just keeps the last N formatted lines in memory
    so the Owner Panel can show them — no external log service needed."""

    def emit(self, record):
        try:
            msg = self.format(record)
        except Exception:
            return
        _all_logs.append(msg)
        if record.levelno >= logging.ERROR:
            _error_logs.append(msg)


log_handler = PanelLogHandler()
log_handler.setLevel(logging.INFO)
log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"))


def _format_log_block(lines: list, empty_msg: str) -> str:
    if not lines:
        return empty_msg
    shown = lines[-LOG_LINES_SHOWN:]
    escaped = html.escape("\n".join(shown))
    return f"<pre>{escaped}</pre>"


async def _safe_edit(query, text, reply_markup):
    """edit_message_text, but swallows Telegram's 'message is not modified'
    error (happens on Refresh when nothing new was logged)."""
    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    except BadRequest as e:
        if "not modified" in str(e).lower():
            await query.answer("Koi naya log nahi hai.")
        else:
            raise


# ---------------- /start keyboard ----------------

def home_text() -> str:
    """Shared, professional panel text used both on /start and on 'Main Menu'."""
    return (
        f"🤖 <b>Welcome to {BOT_NAME}!</b>\n"
        f"<i>Group Management, Simplified.</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Aapke Telegram groups ko safe, active aur entertaining rakhne ka all-in-one tool. ⚡\n\n"
        f"🛡️ <b>Key Features:</b>\n"
        f" ├ 🛑 Anti-Spam & Raid Protection\n"
        f" ├ ⚙️ Advanced Filters & Notes\n"
        f" ├ 📈 XP System & Leaderboards\n"
        f" └ 📊 Polls, Games & Much More!\n\n"
        f"✅ <i>Sab kuch ek jagah, bilkul FREE!</i>\n\n"
        f"👇 <b>Neeche se ek option chuno:</b>\n\n"
        f"📢 <b>Updates:</b> @{OFFICIAL_CHANNEL_URL.rsplit('/', 1)[-1]}\n"
        f"🌟 <b>{BOT_CREDIT}</b>"
    )



def start_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    add_url = f"https://t.me/{bot_username}?startgroup=true&admin=delete_messages+restrict_members+invite_users+pin_messages"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add me to your group", url=add_url)],
            [
                InlineKeyboardButton("👥 My Groups", callback_data="pnl:mygroups:0"),
                InlineKeyboardButton("⚙️ Group Settings", callback_data="pnl:mygroups:0"),
            ],
            [InlineKeyboardButton("👑 Owner Panel", callback_data="pnl:owner")],
            [InlineKeyboardButton("📢 Official Channel", url=OFFICIAL_CHANNEL_URL)],
        ]
    )


def _back_to_start_row():
    return [InlineKeyboardButton("🔙 Main Menu", callback_data="pnl:home")]


async def _send_home(query, context):
    bot_username = (await context.bot.get_me()).username
    await query.edit_message_text(home_text(), parse_mode="HTML", reply_markup=start_keyboard(bot_username))


# ---------------- My Groups / Group Settings picker ----------------

async def _admin_group_ids(context, user_id):
    """Groups the bot is tracked in AND the given user is admin/creator of."""
    result = []
    for g in db.get_all_groups():
        try:
            member = await context.bot.get_chat_member(g["chat_id"], user_id)
            if member.status in ("administrator", "creator"):
                result.append(g)
        except Exception:
            continue
    return result


async def show_my_groups(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    query = update.callback_query
    user_id = query.from_user.id

    groups = await _admin_group_ids(context, user_id)
    if not groups:
        await query.edit_message_text(
            "Tumhe abhi koi group nahi mila jahan tum admin ho aur main maujood hoon.\n\n"
            "Pehle mujhe kisi group me admin ke saath add karo.",
            reply_markup=InlineKeyboardMarkup([_back_to_start_row()]),
        )
        return

    start = page * GROUPS_PER_PAGE
    chunk = groups[start:start + GROUPS_PER_PAGE]

    rows = [[InlineKeyboardButton(f"💬 {g['title']}", callback_data=f"pnl:group:{g['chat_id']}")] for g in chunk]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"pnl:mygroups:{page-1}"))
    if start + GROUPS_PER_PAGE < len(groups):
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"pnl:mygroups:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append(_back_to_start_row())

    await query.edit_message_text(
        f"👥 <b>Tumhare Groups</b> ({len(groups)})\n\nSettings kholne ke liye group chuno:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )


def _group_settings_text(title: str):
    return f"⚙️ <b>Group Settings</b>\n💬 {title}\n\nToggle karne ke liye button dabao:"


def _group_settings_keyboard(chat_id: int):
    rows = []
    for key, (label, emoji, getter, _setter) in TOGGLES.items():
        state = "✅" if getter(chat_id) else "❌"
        rows.append([InlineKeyboardButton(f"{state} {emoji} {label}", callback_data=f"pnl:toggle:{chat_id}:{key}")])
    rows.append([InlineKeyboardButton("🔙 My Groups", callback_data="pnl:mygroups:0")])
    return InlineKeyboardMarkup(rows)


async def show_group_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    query = update.callback_query
    user_id = query.from_user.id

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ("administrator", "creator"):
            await query.answer("Ye group tumhare admin rights me nahi hai.", show_alert=True)
            return
        chat = await context.bot.get_chat(chat_id)
        title = chat.title or "Group"
    except Exception:
        await query.answer("Group access nahi mil paya (bot ab wahan nahi hai?).", show_alert=True)
        return

    await query.edit_message_text(
        _group_settings_text(title), parse_mode="HTML", reply_markup=_group_settings_keyboard(chat_id)
    )


async def toggle_group_setting(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, key: str):
    query = update.callback_query
    user_id = query.from_user.id

    if key not in TOGGLES:
        await query.answer("Unknown setting.", show_alert=True)
        return

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status not in ("administrator", "creator"):
            await query.answer("Ye group tumhare admin rights me nahi hai.", show_alert=True)
            return
        chat = await context.bot.get_chat(chat_id)
        title = chat.title or "Group"
    except Exception:
        await query.answer("Group access nahi mil paya.", show_alert=True)
        return

    label, _emoji, getter, setter = TOGGLES[key]
    new_state = not getter(chat_id)
    setter(chat_id, new_state)
    await query.answer(f"{label}: {'ON ✅' if new_state else 'OFF ❌'}")

    await query.edit_message_text(
        _group_settings_text(title), parse_mode="HTML", reply_markup=_group_settings_keyboard(chat_id)
    )


# ---------------- Owner Panel ----------------

def _is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


def owner_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 Bot Stats", callback_data="pnl:ostats")],
            [InlineKeyboardButton("📢 Broadcast", callback_data="pnl:obroadcast")],
            [InlineKeyboardButton("🗂️ All Groups", callback_data="pnl:ogroups:0")],
            [InlineKeyboardButton("🧾 Live Logs", callback_data="pnl:ologs")],
            [InlineKeyboardButton("🐞 Errors", callback_data="pnl:oerrors")],
            _back_to_start_row(),
        ]
    )


async def show_owner_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return

    await query.edit_message_text(
    text=(
        f"👑 <b>{BOT_NAME} | Administrator Dashboard</b>\n\n"
        f"Welcome back, Master! ⚡\n"
        f"Manage your bot, configure settings, and view system statistics directly from this control panel.\n\n"
        f"⚙️ <b>Panel Access:</b> <code>Owner Only</code>\n\n"
        f"📢 <b>Official Updates:</b> {OFFICIAL_CHANNEL_URL}\n"
        f"🛡️ <b>Credits:</b> {BOT_CREDIT}"
    ),
    parse_mode="HTML",
    reply_markup=owner_keyboard(),
)



async def show_owner_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return

    s = db.get_bot_wide_stats()
    text = (
        f"📊 <b>Bot Stats</b>\n\n"
        f"🗂️ Groups: <b>{s['groups']}</b>\n"
        f"👤 Tracked users: <b>{s['users']}</b>\n"
        f"💬 Total messages seen: <b>{s['messages']}</b>\n"
        f"⌨️ Commands used: <b>{s['commands']}</b>"
    )
    await query.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Owner Panel", callback_data="pnl:owner")]]),
    )


async def show_owner_groups(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return

    groups = db.get_all_groups()
    if not groups:
        await query.edit_message_text(
            "Bot abhi kisi group me nahi hai.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Owner Panel", callback_data="pnl:owner")]]),
        )
        return

    start = page * GROUPS_PER_PAGE
    chunk = groups[start:start + GROUPS_PER_PAGE]
    rows = [
        [
            InlineKeyboardButton(f"💬 {g['title']}", callback_data="pnl:noop"),
            InlineKeyboardButton("🚪 Leave", callback_data=f"pnl:leave:{g['chat_id']}"),
        ]
        for g in chunk
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"pnl:ogroups:{page-1}"))
    if start + GROUPS_PER_PAGE < len(groups):
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"pnl:ogroups:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔙 Owner Panel", callback_data="pnl:owner")])

    await query.edit_message_text(
        f"🗂️ <b>All Groups</b> ({len(groups)})",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def leave_group(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
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


async def show_owner_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await _safe_edit(query, text, kb)


async def show_owner_errors(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await _safe_edit(query, text, kb)


async def clear_owner_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return
    _all_logs.clear()
    await query.answer("Logs clear kar diye ✅")
    await show_owner_logs(update, context)


async def clear_owner_errors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await query.answer("Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return
    _error_logs.clear()
    await query.answer("Errors clear kar diye ✅")
    await show_owner_errors(update, context)


async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
