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

import asyncio
import html
import logging
from collections import deque

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import database as db
from config import BOT_NAME, BOT_CREDIT, OWNER_IDS, OFFICIAL_CHANNEL_URL

GROUPS_PER_PAGE = 8
LOG_LINES_SHOWN = 30
LOG_BUFFER_SIZE = 300
MAX_MESSAGE_CHARS = 3500

logger = logging.getLogger(__name__)

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


async def _safe_answer(query, text: str = None, show_alert: bool = False):
    """query.answer() safely call karo — Telegram callback queries sirf
    ~15-30 sec valid rehte hain, aur ek query pe sirf EK baar answer() ho
    sakta hai. Agar processing slow ho jaaye (Turso/network delay) to
    answer() 'too old' ya 'already answered' error de sakta hai — pehle
    ye crash kara raha tha (on_error handler tak jaata tha). Ab silently
    log ho ke ignore hoga, bot crash nahi karega."""
    try:
        if text:
            await query.answer(text, show_alert=show_alert)
        else:
            await query.answer()
    except BadRequest as e:
        logger.warning("query.answer() fail (ignored, likely expired): %s", e)
    except Exception as e:
        logger.warning("query.answer() unexpected fail (ignored): %s", e)


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
        [
          InlineKeyboardButton("📢 Official Channel", url=OFFICIAL_CHANNEL_URL),
          InlineKeyboardButton("Help Center", url="https://teamvb-manager-bot.netlify.app/"),
        ],
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
    for g in (await db.get_all_groups())[:50]:
        try:
            m = await context.bot.get_chat_member(g["chat_id"], user_id)
            if m.status in ("administrator", "creator"):
                mine.append(g)
        except Exception:
            continue
    return mine


async def _is_group_admin(context, user_id: int) -> bool:
    if _is_owner(user_id):
        return True
    try:
        return True  # mygroups screen khud filter karti hai
    except Exception:
        return False


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


async def show_group_settings(update, context, chat_id: int):
    """Old flat toggle panel — ab bhi 'My Groups' se accessible (compatibility)."""
    query = update.callback_query
    kb = []
    for key, (label, emoji, getter, _setter) in TOGGLES.items():
        try:
            state = bool(await getter(chat_id))
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
        await _safe_answer(query, "Setting nahi mili 🤔", show_alert=True)
        return
    label, emoji, getter, setter = TOGGLES[key]
    try:
        new_val = not bool(await getter(chat_id))
        await setter(chat_id, new_val)
    except Exception:
        await _safe_answer(query, "❌ Nahi hua — dobara try karo", show_alert=True)
        return
    await _safe_answer(query, f"{emoji} {label}: {'✅ ON' if new_val else '❌ OFF'}")
    await show_group_settings(update, context, chat_id)


# ---------------- Owner Panel ----------------

def _fmt_num(n: int) -> str:
    return f"{n:,}"


async def show_owner_panel(update, context):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await _safe_answer(query, "Ye panel sirf bot owner ke liye hai.", show_alert=True)
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
        await _safe_answer(query, "Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return
    s = await db.get_bot_wide_stats()
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
        await _safe_answer(query, "Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return
    groups = await db.get_all_groups()
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
        await _safe_answer(query, "Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return
    try:
        await context.bot.leave_chat(chat_id)
    except Exception:
        pass
    await db.remove_group(chat_id)
    await _safe_answer(query, "Group leave kar diya.")
    await show_owner_groups(update, context, page=0)


# ---------------- Live Logs / Errors (overflow-safe) ----------------

def _format_log_block(lines, empty_msg: str) -> str:
    """Last N log lines, but never exceed Telegram's message limit."""
    if not lines:
        return f"<i>{empty_msg}</i>"
    result_lines = []
    total = 0
    for line in reversed(lines):
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
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await _safe_answer(query, "Ye panel sirf bot owner ke liye hai.", show_alert=True)
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
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await _safe_answer(query, "Ye panel sirf bot owner ke liye hai.", show_alert=True)
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


async def _edit_or_alert(query, text, kb):
    """Edit karo; agar content same hai to chup raho, warna user ko error dikhao."""
    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            await _safe_answer(query, f"⚠️ {str(e)[:180]}", show_alert=True)
    except Exception as e:
        await _safe_answer(query, f"⚠️ {str(e)[:180]}", show_alert=True)


async def clear_owner_logs(update, context):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await _safe_answer(query, "Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return
    _all_logs.clear()
    await show_owner_logs(update, context)


async def clear_owner_errors(update, context):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await _safe_answer(query, "Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return
    _error_logs.clear()
    await show_owner_errors(update, context)


async def start_broadcast(update, context):
    query = update.callback_query
    if not _is_owner(query.from_user.id):
        await _safe_answer(query, "Ye panel sirf bot owner ke liye hai.", show_alert=True)
        return

    context.user_data["broadcast_step"] = "text"
    context.user_data["broadcast_data"] = {}
    await query.edit_message_text(
        "📢 <b>Broadcast — Step 1/3: Text</b>\n\n"
        "Message likho jo bhejna hai.\n\n"
        "⏭️ /skip — sirf media/button bhejna hai, text nahi\n"
        "❌ /cancel — poora process cancel karo",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Owner Panel", callback_data="pnl:owner")]]),
    )


async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Called from bot.py's private-chat text/media/command handlers.
    3-step broadcast wizard: text -> media -> buttons -> send.
    Returns True if this message was consumed by the wizard."""
    step = context.user_data.get("broadcast_step")
    if not step:
        return False

    user_id = update.effective_user.id
    if not _is_owner(user_id):
        context.user_data.pop("broadcast_step", None)
        context.user_data.pop("broadcast_data", None)
        return False

    msg = update.effective_message
    text = (msg.text or "").strip() if msg.text else ""

    # /cancel — kisi bhi step pe kaam karega
    if text == "/cancel":
        context.user_data.pop("broadcast_step", None)
        context.user_data.pop("broadcast_data", None)
        await msg.reply_text("❌ Broadcast cancel kar diya.")
        return True

    data = context.user_data.setdefault("broadcast_data", {})

    # ---------- Step 1: TEXT ----------
    if step == "text":
        if text == "/skip":
            data["text"] = None
        elif text:
            data["text"] = text
        else:
            await msg.reply_text("❌ Text bhejo, ya /skip karo.")
            return True
        context.user_data["broadcast_step"] = "media"
        await msg.reply_text(
            "📢 <b>Step 2/3: Media</b>\n\n"
            "Photo/video/document/GIF bhejo.\n\n"
            "⏭️ /skip — bina media ke aage badho\n"
            "❌ /cancel — cancel karo",
            parse_mode="HTML",
        )
        return True

    # ---------- Step 2: MEDIA ----------
    if step == "media":
        if text == "/skip":
            data["media_type"] = None
            data["file_id"] = None
        elif msg.photo:
            data["media_type"] = "photo"
            data["file_id"] = msg.photo[-1].file_id
        elif msg.video:
            data["media_type"] = "video"
            data["file_id"] = msg.video.file_id
        elif msg.animation:
            data["media_type"] = "animation"
            data["file_id"] = msg.animation.file_id
        elif msg.document:
            data["media_type"] = "document"
            data["file_id"] = msg.document.file_id
        else:
            await msg.reply_text("❌ Photo/video/document/GIF bhejo, ya /skip karo.")
            return True
        context.user_data["broadcast_step"] = "buttons"
        await msg.reply_text(
            "📢 <b>Step 3/3: Buttons</b>\n\n"
            "Format (ek line = ek row):\n"
            "<code>Label - https://link.com</code>\n\n"
            "Same row me 2 buttons chahiye toh <code>|</code> se alag karo:\n"
            "<code>Channel - https://t.me/x | Group - https://t.me/y</code>\n\n"
            "⏭️ /skip — bina buttons ke bhej do\n"
            "❌ /cancel — cancel karo",
            parse_mode="HTML",
        )
        return True

    # ---------- Step 3: BUTTONS -> SEND ----------
    if step == "buttons":
        if text == "/skip":
            data["buttons"] = None
        else:
            kb_rows, valid = [], True
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                row = []
                for part in line.split("|"):
                    part = part.strip()
                    if " - " not in part:
                        valid = False
                        break
                    label, url = part.rsplit(" - ", 1)
                    label, url = label.strip(), url.strip()
                    if not label or not url.startswith(("http://", "https://")):
                        valid = False
                        break
                    row.append(InlineKeyboardButton(label, url=url))
                if not valid:
                    break
                if row:
                    kb_rows.append(row)
            if not valid or not kb_rows:
                await msg.reply_text(
                    "❌ Format galat hai. Example:\n"
                    "<code>Channel - https://t.me/theteamvb</code>\n\n"
                    "Ya /skip karo.",
                    parse_mode="HTML",
                )
                return True
            data["buttons"] = kb_rows

        if not data.get("text") and not data.get("media_type"):
            context.user_data.pop("broadcast_step", None)
            context.user_data.pop("broadcast_data", None)
            await msg.reply_text("❌ Text aur media dono skip kar diye — kuch bhejne ko hi nahi bacha. Broadcast cancel ho gaya.")
            return True

        context.user_data.pop("broadcast_step", None)
        await _send_broadcast(msg, context, data)
        context.user_data.pop("broadcast_data", None)
        return True

    return False


async def _send_broadcast(msg, context, data):
    """Media pehle, text caption ke roop me, buttons attached — sabhi groups me."""
    groups = await db.get_all_groups()
    sent, failed = 0, 0
    kb = InlineKeyboardMarkup(data["buttons"]) if data.get("buttons") else None
    text = data.get("text")
    media_type = data.get("media_type")
    file_id = data.get("file_id")

    status_msg = await msg.reply_text(f"📤 Broadcast bhej raha hoon... (0/{len(groups)})")

    for i, g in enumerate(groups, 1):
        try:
            if media_type == "photo":
                await context.bot.send_photo(g["chat_id"], file_id, caption=text, parse_mode="HTML" if text else None, reply_markup=kb)
            elif media_type == "video":
                await context.bot.send_video(g["chat_id"], file_id, caption=text, parse_mode="HTML" if text else None, reply_markup=kb)
            elif media_type == "animation":
                await context.bot.send_animation(g["chat_id"], file_id, caption=text, parse_mode="HTML" if text else None, reply_markup=kb)
            elif media_type == "document":
                await context.bot.send_document(g["chat_id"], file_id, caption=text, parse_mode="HTML" if text else None, reply_markup=kb)
            else:
                await context.bot.send_message(g["chat_id"], text, parse_mode="HTML", reply_markup=kb)
            sent += 1
        except Exception:
            failed += 1

        if i % 20 == 0:
            try:
                await status_msg.edit_text(f"📤 Broadcast bhej raha hoon... ({i}/{len(groups)})")
            except Exception:
                pass
        await asyncio.sleep(0.05)  # flood-limit safety

    await status_msg.edit_text(f"📢 <b>Broadcast complete!</b>\n\n✅ Sent: {sent}\n❌ Failed: {failed}", parse_mode="HTML")


# ---------------- Callback router ----------------

async def on_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Sabse PEHLE answer — Telegram callback queries sirf ~15-30 sec valid
    # rehte hain. Purane order me har function apne end pe answer() karta
    # tha, jisse slow processing (Turso/network delay) ke case me
    # "Query is too old" crash aata tha. Ab turant ack ho jaayega, chahe
    # baaki processing (DB reads, edits) jitni bhi der le.
    await _safe_answer(query)

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
