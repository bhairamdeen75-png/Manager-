"""Security+ — group ko bulletproof banane ke liye. Funny Hinglish warnings included.

Features:
/checkperms — bot permissions audit
Suspicious username filter (auto)
Media spam filter (10s me 4+ = mute)
Malicious file blocker (.exe/.apk...)
URL whitelist (/allowdomain)
Bot-detection (bina admin approve ke bot aaya to kick)
Demotion alert (bot ko demote kiya to shor)
/securitystatus — security dashboard
Sequential-join detection (User123, User124...)
Night-lock hardening (night mode me media block)
/quarantine — naye members 24h tak restricted
"""

import logging
import random
import re
import time
from datetime import datetime, timedelta, timezone

from telegram import Update, ChatPermissions
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin

logger = logging.getLogger(__name__)

# ================= FUNNY LINES (bot ki mazakiya language) =================

FUNNY = {
    "perms_ok": [
        "🔥 Sab permissions on hain — main ab poora don hoon!",
        "✅ Full power mode! Thanos bhi proud ho jaye.",
        "😎 Rights poori hain, ab koi aayega to seedha utha lunga.",
    ],
    "perms_missing": [
        "🥲 Boss thoda pyaar karo, ye permissions to de do...",
        "😭 Main bechara hoon, ye rights do to danga karta hoon!",
        "🥺 Admin rights adhoori hain — main aadha Robot hai bas.",
    ],
    "not_admin": [
        "🤨 Bhai pehle mujhe admin banao, phir baat karenge.",
        "😅 Pehle rights do, phir gaane gaun.",
    ],
    "media_spam": [
        "📸 Bhai photo studio khol liya kya? Chal 5 min break le. 🔇",
        "🖼️ Itni photos mat daal, gallery bhar gaya mera! 5 min mute.",
        "🤳 Selfie queen/king — thoda kam kar! 5 min ka time-out.",
    ],
    "night_media": [
        "🌙 Bhai raat hai, photos ka mela nahi chal raha. Delete ho gaya.",
        "🌃 Night mode ON hai — media so raha hai, tu bhi so ja.",
    ],
    "bad_file": [
        "☣️ Ye file to virus lag rahi hai! Delete kar diya, sorry not sorry.",
        "🦠 .exe/.apk? Yahan bas memes allowed hain. File gayi.",
        "🗑️ Suspicious file pakdi gayi — dustbin me daal diya.",
    ],
    "url_block": [
        "🔗 Ye domain whitelist me nahi hai — bye bye link!",
        "🚫 Ye link suspicious lag raha hai, maine uda diya.",
        "🌐 Sirf trusted links chalenge bhai, ye kata jaata hai.",
    ],
    "bot_joined": [
        "🤖 Ek naya bot ghusa hai! Admin ne bheja hai, dekh lo.",
    ],
    "bot_kicked": [
        "🥾 Bina permission ke bot ghusa — nikal phirst! Bot ko kick kar diya.",
        "🚪 Random bot? Yahan entry nahi. Kick ho gaya.",
    ],
    "demoted": [
        "😱 Arre! Kisi ne mohabbat ka maara, mujhe demote kar diya!",
        "🚨 Mera admin rights chin liya gaya! Owner bhai, dekh le!",
        "💔 Main ab aam member ban gaya... koi wapas rights dilayega?",
    ],
    "raid_pattern": [
        "🕵️ Ye joins suspicious hain — User123, User124... bot farm lag raha hai!",
        "🚨 Serial joins pakde gaye! Koi raid attempt kar raha hai shayad.",
    ],
    "quarantine_media": [
        "🧊 Abhi tum quarantine me ho naye member — 24h baad media khulega.",
        "⏳ Naya member ho, pehle bharosa karo, phir memes bhejna.",
    ],
    "sus_name": [
        "🎭 Iska naam to theek nahi lag raha... restrict kar diya, admin dekh le.",
        "🚩 Shady username detected! Verification me rakh diya.",
    ],
}

def _funny(key: str) -> str:
    return random.choice(FUNNY[key])

# ================= IN-MEMORY STATE =================

_media_log: dict = {}          # (chat_id, user_id) -> [timestamps]
_join_time: dict = {}          # (chat_id, user_id) -> epoch (quarantine ke liye)
_name_log: dict = {}           # chat_id -> [ (time, name) ]
_stats: dict = {}              # chat_id -> {"deleted": int, "mutes": int, "files": int, "links": int}

def _bump(chat_id, key):
    _stats.setdefault(chat_id, {"deleted": 0, "mutes": 0, "files": 0, "links": 0})
    _stats[chat_id][key] = _stats[chat_id].get(key, 0) + 1

# ================= DB HELPERS (settings_col direct — database.py me change nahi karna) =================

def _get(chat_id, key, default):
    doc = db.settings_col.find_one({"chat_id": chat_id})
    return doc.get(key, default) if doc else default

def _set(chat_id, key, value):
    db.settings_col.update_one({"chat_id": chat_id}, {"$set": {key: value}}, upsert=True)

# ================= 1. /checkperms =================

async def cmd_checkperms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not await is_admin(update, context):
        await update.message.reply_text(_funny("not_admin"))
        return
    try:
        me = await context.bot.get_chat_member(chat.id, context.bot.id)
        if me.status == "member":
            await update.message.reply_text(
                "❌ Main admin bhi nahi hoon! 🥲\n" + _funny("perms_missing")
            )
            return
        if me.status != "administrator":
            await update.message.reply_text("🤔 Status ajeeb hai: " + me.status)
            return

        # PTB v21 me permissions seedhe ChatMemberAdministrator pe hoti hain
        perms = {
            "Delete messages": me.can_delete_messages,
            "Ban/Mute users": me.can_restrict_members,
            "Pin messages": me.can_pin_messages,
            "Invite via link": me.can_invite_users,
        }
        lines = [f"{'✅' if v else '❌'} {k}" for k, v in perms.items()]
        missing = [k for k, v in perms.items() if not v]
        text = "🔐 <b>Meri powers ka audit:</b>\n" + "\n".join(lines)
        if missing:
            text += (
                "\n\n⚠️ Ye missing hain boss — inke bina main half talwar hoon:\n<b>"
                + ", ".join(missing)
                + "</b>\n\n" + _funny("perms_missing")
            )
        else:
            text += "\n\n" + _funny("perms_ok")
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.exception("checkperms fail")
        await update.message.reply_text(f"❌ Audit fail: {e}")
        
# ================= 2. Suspicious username filter =================

_SUSPICIOUS_PATTERNS = re.compile(
    r"(porn|xxx|sex|casino|bet|satta|hack|fuck|sexy|girl\b|hot\W|escort|call.?girl"
    r"|[\u200b\u200c\u200d\u2060\ufeff])",   # zero-width/invisible chars
    re.IGNORECASE,
)

async def check_suspicious_name(update: Update, context: ContextTypes.DEFAULT_TYPE, member) -> bool:
    """True agar naam shady tha aur action le liya."""
    chat = update.effective_chat
    name = (member.first_name or "") + " " + (member.last_name or "")
    if not _SUSPICIOUS_PATTERNS.search(name):
        return False
    try:
        await context.bot.restrict_chat_member(
            chat.id, member.id,
            permissions=ChatPermissions(can_send_messages=False),
        )
        _bump(chat.id, "mutes")
        await context.bot.send_message(
            chat.id, _funny("sus_name"), parse_mode=ParseMode.HTML,
        )
        return True
    except Exception:
        return False

# ================= 3. Media spam filter + 10. Night-lock hardening + 12. Quarantine =================

async def on_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Photo/GIF/video/sticker/voice — sab yahan se guzrega."""
    chat, user, msg = update.effective_chat, update.effective_user, update.effective_message
    if not chat or not user or chat.type not in ("group", "supergroup"):
        return
    try:
        m = await context.bot.get_chat_member(chat.id, user.id)
        if m.status in ("administrator", "creator"):
            return
    except Exception:
        return

    # 10. Night-lock hardening — night mode me non-admin media delete
    if db.get_night_mode(chat.id):
        try:
            await msg.delete()
            _bump(chat.id, "deleted")
            await context.bot.send_message(chat.id, _funny("night_media"))
        except Exception:
            pass
        return

    # 12. Quarantine — naye members (<24h) media nahi bhej sakte
    if _get(chat.id, "quarantine", False):
        jt = _join_time.get((chat.id, user.id))
        if jt and (time.time() - jt) < 86400:
            try:
                await msg.delete()
                _bump(chat.id, "deleted")
                await msg.reply_text(_funny("quarantine_media"))
            except Exception:
                pass
            return

    # 3. Media spam — 10 sec me 4+
    now = time.time()
    key = (chat.id, user.id)
    ts = [t for t in _media_log.get(key, []) if now - t < 10]
    ts.append(now)
    _media_log[key] = ts
    if len(ts) < 4:
        return
    _media_log[key] = []
    try:
        await msg.delete()
        _bump(chat.id, "deleted")
    except Exception:
        return
    until = datetime.now(timezone.utc) + timedelta(minutes=5)
    try:
        await context.bot.restrict_chat_member(
            chat.id, user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        _bump(chat.id, "mutes")
        await context.bot.send_message(
            chat.id, _funny("media_spam"), parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

# ================= 4. Malicious file blocker =================

BAD_EXTS = {".exe", ".apk", ".scr", ".bat", ".cmd", ".msi", ".jar", ".com", ".pif"}

async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, user, msg = update.effective_chat, update.effective_user, update.effective_message
    doc = msg.document if msg else None
    if not chat or not user or not doc or chat.type not in ("group", "supergroup"):
        return
    try:
        m = await context.bot.get_chat_member(chat.id, user.id)
        if m.status in ("administrator", "creator"):
            return
    except Exception:
        return
    fname = (doc.file_name or "").lower()
    if not any(fname.endswith(ext) for ext in BAD_EXTS):
        return
    try:
        await msg.delete()
        _bump(chat.id, "files")
        await context.bot.send_message(
            chat.id,
            f"☣️ <b>{fname}</b> — {user.mention_html()}\n" + _funny("bad_file"),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

# ================= 5. URL whitelist =================

_URL_RE = re.compile(r"(?:https?://|www\.|t\.me/)([a-z0-9.-]+)", re.IGNORECASE)

def _get_whitelist(chat_id):
    return _get(chat.id if False else chat_id, "url_whitelist", [])
_get_whitelist = lambda chat_id: _get(chat_id, "url_whitelist", [])  # noqa

async def cmd_allowdomain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text(_funny("not_admin"))
        return
    if not context.args:
        await update.message.reply_text("Use karo: /allowdomain youtube.com\nEk waqt me ek domain. List dekhne ke liye /alloweddomains")
        return
    domain = context.args[0].lower().strip().lstrip("@")
    wl = _get(update.effective_chat.id, "url_whitelist", [])
    if domain in wl:
        await update.message.reply_text(f"😅 {domain} pehle se allowed hai bhai.")
        return
    wl.append(domain)
    _set(update.effective_chat.id, "url_whitelist", wl)
    await update.message.reply_text(f"✅ <b>{domain}</b> ab allowed hai! Baaki links kate jayenge. 😎", parse_mode=ParseMode.HTML)

async def cmd_removedomain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text(_funny("not_admin"))
        return
    if not context.args:
        await update.message.reply_text("Use karo: /removedomain youtube.com")
        return
    domain = context.args[0].lower().strip()
    wl = _get(update.effective_chat.id, "url_whitelist", [])
    if domain in wl:
        wl.remove(domain)
        _set(update.effective_chat.id, "url_whitelist", wl)
        await update.message.reply_text(f"🗑️ {domain} hata diya. Ab iske links kate jayenge!")
    else:
        await update.message.reply_text("Ye domain list me hai hi nahi bhai.")

async def cmd_alloweddomains(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wl = _get(update.effective_chat.id, "url_whitelist", [])
    if not wl:
        await update.message.reply_text("🌐 Whitelist khali hai — matlab sab links allowed. Set karne ke liye /allowdomain youtube.com")
        return
    await update.message.reply_text("🌐 <b>Allowed domains:</b>\n" + "\n".join(f"• {d}" for d in wl), parse_mode=ParseMode.HTML)

async def check_url_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Text messages me URL check — whitelist set hai to non-whitelisted links delete."""
    chat, user, msg = update.effective_chat, update.effective_user, update.effective_message
    if not chat or not user or not msg or not msg.text or chat.type not in ("group", "supergroup"):
        return
    wl = _get(chat.id, "url_whitelist", [])
    if not wl:
        return  # whitelist off
    try:
        m = await context.bot.get_chat_member(chat.id, user.id)
        if m.status in ("administrator", "creator"):
            return
    except Exception:
        return
    # Quarantine: naye members whitelist ki chinta nahi, sab links band
    if _get(chat.id, "quarantine", False):
        jt = _join_time.get((chat.id, user.id))
        if jt and (time.time() - jt) < 86400:
            try:
                await msg.delete()
                _bump(chat.id, "deleted")
                await msg.reply_text(_funny("quarantine_media"))
            except Exception:
                pass
            return
    domains = _URL_RE.findall(msg.text)
    for d in domains:
        d = d.lower()
        if not any(d == w or d.endswith("." + w) for w in wl):
            try:
                await msg.delete()
                _bump(chat.id, "links")
                await context.bot.send_message(chat.id, _funny("url_block"))
            except Exception:
                pass
            return

# ================= 6. Bot detection (naya member bot hai to) =================

async def check_joining_bot(update: Update, context: ContextTypes.DEFAULT_TYPE, member) -> bool:
    """Naya member bot hai aur usne jodne wala admin nahi — kick + alert. True = handled."""
    chat = update.effective_chat
    adder = update.effective_message.from_user
    if not adder:
        return False
    if await is_admin(update, context, user_id=adder.id):
        await context.bot.send_message(
            chat.id, _funny("bot_joined") + f"\n🤖 <b>{member.first_name}</b> (added by <b>{adder.first_name}</b>)",
            parse_mode=ParseMode.HTML,
        )
        return True
    # Non-admin ne bot add kiya — kick it
    try:
        await context.bot.ban_chat_member(chat.id, member.id)
        await context.bot.unban_chat_member(chat.id, member.id)
        await context.bot.send_message(chat.id, _funny("bot_kicked"), parse_mode=ParseMode.HTML)
    except Exception:
        pass
    return True

# ================= 7. Demotion alert =================

async def on_my_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot ka apna status badla — demotion pakdo."""
    cm = update.my_chat_member
    if not cm:
        return
    chat = update.effective_chat
    old_s = cm.old_chat_member.status
    new_s = cm.new_chat_member.status
    if old_s == "administrator" and new_s not in ("administrator", "creator", "left", "kicked"):
        try:
            await context.bot.send_message(chat.id, _funny("demoted"), parse_mode=ParseMode.HTML)
        except Exception:
            pass
    if new_s == "administrator":
        try:
            await context.bot.send_message(chat.id, "🎉 Wapas admin ban gaya! Full power restored 💪")
        except Exception:
            pass

# ================= 8. /securitystatus =================

async def cmd_securitystatus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text(_funny("not_admin"))
        return
    chat_id = update.effective_chat.id
    s = _stats.get(chat_id, {"deleted": 0, "mutes": 0, "files": 0, "links": 0})
    wl = _get(chat_id, "url_whitelist", [])
    quar = _get(chat_id, "quarantine", False)
    night = db.get_night_mode(chat_id)
    raid = db.get_raid_protection(chat_id)
    text = (
        "🛡️ <b>Security Dashboard</b> 🛡️\n\n"
        f"🗑️ Deleted messages: <b>{s['deleted']}</b>\n"
        f"🔇 Mutes: <b>{s['mutes']}</b>\n"
        f"☣️ Blocked files: <b>{s['files']}</b>\n"
        f"🔗 Blocked links: <b>{s['links']}</b>\n\n"
        f"🛡️ Raid protection: {'✅' if raid else '❌'}\n"
        f"🌙 Night mode: {'✅ (media bhi blocked)' if night else '❌'}\n"
        f"🧊 Quarantine: {'✅' if quar else '❌'}\n"
        f"🌐 URL whitelist: {'✅ (' + str(len(wl)) + ' domains)' if wl else '❌ (sab allowed)'}\n\n"
        "💡 Tip: /checkperms se meri powers check karo!"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ================= 9. Sequential-join detection =================

_SEQ_RE = re.compile(r"^(.*?)(\d{2,})$")  # trailing 2+ digits

async def check_join_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE, member) -> bool:
    """User123/User124 jaise serial names 60s me 3+ — alert. True = suspicious."""
    chat = update.effective_chat
    name = member.first_name or ""
    m = _SEQ_RE.match(name)
    if not m:
        return False
    prefix = m.group(1).lower().strip()
    now = time.time()
    log = _name_log.setdefault(chat.id, [])
    log[:] = [(t, p) for (t, p) in log if now - t < 60]
    log.append((now, prefix))
    same = [p for (_, p) in log if p == prefix]
    if len(same) >= 3:
        _name_log[chat.id] = []
        try:
            admins = await chat.get_administrators()
            tags = " ".join(a.user.mention_html() for a in admins if not a.user.is_bot)
            await context.bot.send_message(
                chat.id,
                f"🕵️ <b>Suspicious joins!</b> <b>{len(same)}x '{prefix}***'</b> pattern pakda — ye bot farm lag raha hai!\n{tags} dekh lo bhai!",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass
        return True
    return False

# ================= 12. /quarantine =================

async def cmd_quarantine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text(_funny("not_admin"))
        return
    if not context.args or context.args[0].lower() not in ("on", "off"):
        cur = "on" if _get(update.effective_chat.id, "quarantine", False) else "off"
        await update.message.reply_text(f"🧊 Use karo: /quarantine on|off\nCurrent: <b>{cur}</b>\n\nQuarantine ON = naye members 24h tak sirf text bhej sakte hain (no links/media/files). Bina bharose wale ke liye perfect! 😏", parse_mode=ParseMode.HTML)
        return
    enabled = context.args[0].lower() == "on"
    _set(update.effective_chat.id, "quarantine", enabled)
    if enabled:
        await update.message.reply_text("🧊 Quarantine ON! Naye members 24h tak probation par hain — pehle bharosa, phir masti. 😎")
    else:
        await update.message.reply_text("🧊 Quarantine OFF. Sab azaad ho gaye!")

# ================= New member hook (2, 6, 9 + join-time tracking) =================

async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return
    for member in update.effective_message.new_chat_members:
        if member.is_bot:
            await check_joining_bot(update, context, member)
            continue
        _join_time[(chat.id, member.id)] = time.time()
        await check_suspicious_name(update, context, member)
        await check_join_pattern(update, context, member)
