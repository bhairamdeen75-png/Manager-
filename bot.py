import logging
import random

from telegram import Update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ChatJoinRequestHandler,
    ContextTypes,
    filters,
)

from config import (
    BOT_TOKEN, BOT_NAME, BOT_CREDIT,
    XP_MIN_PER_MESSAGE, XP_MAX_PER_MESSAGE, XP_COOLDOWN_SECONDS,LEADERBOARD_INTERVAL_MINUTES,
)
import database as db
from keep_alive import keep_alive

from handlers import (
    moderation,
    antispam,
    filters_handler,
    captcha,
    welcome,
    content_filter,
    logs,
    nightmode,
    rules,
    joinleave,
    raid,
    info,
    notes,
    tagall,
    autopin,
    autoresponses,
    pomodoro,
    reminders,
    dictionary,
    xp,
    polls,
    stats,
    panel,
    adminplus,
    # ===== NAYE MODULES =====
    store,
    spamscore,
    channelspam,
    captchaplus,
    appeals,
    backup,
    invites,
    welcomemedia,
    translate,
    aliases,
    scheduler,
    approve,
    activity,
    antiedit,
    gban,
    antiforward,
    blocklist,
    security,
    settings_panel,
    extra2,
    smartreply,
    music,
    fun,
    autoreact,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
logging.getLogger().addHandler(panel.log_handler)  # feeds Owner Panel → Live Logs / Errors


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = (await context.bot.get_me()).username
    await update.message.reply_text(
        panel.home_text(), parse_mode="HTML", reply_markup=panel.start_keyboard(bot_username)
    )

HELP_PAGES = {
    "basic": (
        "🟢 <b>BASIC COMMANDS</b> <i>(sabke liye)</i>\n"
        "<i>\"Yahan se shuru hota hai asli kaam.\" 😎</i>\n\n"
        "👋 /start — control panel kholo\n"
        "👋 /help — ye help menu (obviously tum yahi padh rahe ho 🤔)\n\n"
        "👮 <b>Moderation</b> <i>(reply karke use karo)</i>\n"
        "👮 /mute — bakte user ko maun vrat 🤐\n"
        "👮 /unmute — bolne do, azaadi! 🕊️\n"
        "👮 /kick — group se bahar, dhakke ke saath 👋\n"
        "👮 /warn — pehli warning, sharif warning\n"
        "👮 /warnings — kisko kitni mili, hisab kitab 📋\n\n"
        "📢 <b>Mastauri Section:</b>\n"
        "📢 /tagall — sabko tag karo, sab jagega 😴➡️😳\n\n"
        "📝 <b>Notes:</b>\n"
        "📝 /save &lt;name&gt; (reply karke) — note banao\n"
        "📝 #name — note kholo, kabhi bhi\n"
        "<i>💡 Hint: note name chhota rakho, yaad rakhna easy hota hai</i>\n\n"
        "🎯 <b>Fun & Info:</b>\n"
        "🎵 /play - Music sunnne ke liye vc chalao phir sunte hai \n"
        "📊 /rank — apna XP dekho, competition toh banta hai 💪\n"
        "🏆 /leaderboard — top users, jalan bhi sath me free\n"
        "🎲 /poll — poll banao, group ki raay jaano\n"
        "🧠 /quiz — quiz banao, dimag ki batti jalaо 💡\n"
        "📖 /define &lt;word&gt; — meaning dekho, dictionary wala bhai\n"
        "⏰ /remindme &lt;time&gt; &lt;text&gt; — bhoolne walon ke liye special 🧠\n"
        "🌤️ /weather &lt;city&gt; — mausam dekho\n"
        "📚 /wiki &lt;topic&gt; — Wikipedia se gyan\n"
        "🧮 /calc &lt;expr&gt; — calculator\n"
        "🎮 /guess — guessing game khelo\n"
        "🎭 /roast — reply karke funny roast\n"
        "🌟 /compliment — reply karke tareef\n"
        "🔮 /fortune — mazakiya bhavishyavani\n"
        "🚨 /ticket — funny police ticket\n"
        "🔢 /count — group counting game\n"
        "⭐ /rep + / /rep - — reputation\n"
        "🎨 /emojistory — emoji story contest\n"
        "🐾 /pet /feed /play — group pet\n"
        "🤫 /confess — anonymous confession (DM me)\n"
    ),
    "medium": (
        "🟡 <b>MEDIUM COMMANDS</b> <i>(admin level-up)</i>\n"
        "<i>\"Ab tum admin se ustaad ban rahe ho.\" 🥋</i>\n\n"
        "👮 <b>Hard Moderation:</b>\n"
        "👮 /ban — door kar do isko, seedha GHAR BHEJO 🚪\n"
        "👮 /unban &lt;user_id&gt; — galti sudhar li, wapas bula lo\n"
        "👮 /unwarn — warning maaf, dil bada rakho ❤️\n"
        "👮 /status — user ka pura record, police file jaisa 📁\n"
        "👮 /report — problem report karo, mod sahab sun rahe hain 📣\n\n"
        "🛡️ <b>Protection:</b>\n"
        "🛡️ /addfilter — shabd add karo jo group me mana hai\n"
        "🛡️ /removefilter — filter hatao, rehne do\n"
        "🛡️ /filters — saare filters dekho\n"
        "🛡️ /lock — group lock, sab shant 🤫\n"
        "🛡️ /unlock — khol do, bhaag daudo 💨\n"
        "🛡️ /setlinkblock on|off — links block, spam king fail 😈\n"
        "🛡️ /restrictmedia — media par rok, discipline rakho\n"
        "🛡️ /purge — reply karke, messages saaf — jhadu chal gayi 🧹\n\n"
        "⚙️ <b>Setup:</b>\n"
        "⚙️ /setwelcome — naye member ka swagat, VIP style 🎊\n"
        "⚙️ /setleave — jaate waqt alvida, dramatic 🎬\n"
        "⚙️ /setrules — niyam likho, /rules se padhwayo\n"
        "⚙️ /setlogchannel — log channel set karo, CCTV on 📹\n"
        "⚙️ /nightmode — raat ko group so jayega 🌙\n"
        "⚙️ /setnighttime — sone ka time set karo 😴\n"
        "⚙️/smart - smart and auto reply ke liye \n\n"
        "🤖 <b>Automation:</b>\n"
        "🌐 /shorturl &lt;link&gt; — lamba link chhota karo\n"
        "📱 /qr &lt;text&gt; — QR code banao\n"
        "🕐 /time — duniya ka time\n"
        "📝 /addresponse /delresponse /responses — auto-reply, bot khud jawab dega\n"
        "📝 /alias /unalias /aliases — command ka nickname banao\n"
        "📅 /schedule /scheduled /unsched — message time pe bhejo, alarm jaisa ⏰\n"
        "🍅 /pomodoro /pomodorostop — study timer, focus mode on 📚"
    ),
    "advanced": (
        "🔴 <b>ADVANCED COMMANDS</b> <i>(boss level)</i>\n"
        "<i>\"Yahan se pehuncha toh tum pro ho.\" 🕶️</i>\n\n"
        "🛡️ <b>Advanced Protection:</b>\n"
        "🛡️ /raidprotection on|off — raid aaye toh bot sherni ban jayega 🦁\n"
        "🛡️ /setraidlimits &lt;joins&gt; &lt;seconds&gt; &lt;lock_min&gt; — raid limits set karo\n"
        "🛡️ /setcaptchamode math|button|image — captcha style chuno, entry test hoga 🚪\n"
        "🛡️ /approve /unapprove /approved — trusted members list\n"
        "🛡️ /checkperms — mera role check karo, kya mai admin hun? 🤨\n"
        "🛡️ /securitystatus — security ka full report, James Bond style 🕵️\n"
        "🛡️ /quarantine — shak wale user ko隔离 karo 🏥\n"
        "🛡️ /antiforward — channel forward auto-delete 📺❌\n"
        "🛡️/pro - Sari important security ko ek sath open karta hu ek command me\n"
        "🌐 /allowdomain /alloweddomains /removedomain — link whitelist\n"
        "🤖 /autoreact on/off — bot har message pe random reaction lagayega (admin)\n"
        "<i>✏️ Anti-edit spam — automatic hai, tum tension mat lo</i>\n"
        "<i>📺 Anti-channel-spam — automatic hai, bot dekh raha hai</i>\n"
        "<i>🚫 Global blocklist — automatic hai, pahle hi block</i>\n\n"
        "⚙️ <b>Advanced Setup:</b>\n"
        "⚙️ /rulesgate on|off — rules accept karke hi entry milegi 📜\n"
        "⚙️ /autopin — admin messages khud pin 📌\n"
        "⚙️ /autodeletejoinleave on|off — join/leave msg khud delete 🧹\n"
        "⚙️ /setwmedia /setwbtn — welcome me photo aur button 🖼️\n"
        "⚙️ /clearwmedia /clearwbtn — media hatao\n\n"
        "🎉 <b>Fun & Utility:</b>\n"
        "🎉 /invites /invitetop — kisko kitne member laya, competition 🏅\n"
        "📊 /activity — 7-day activity chart, sabki asli performance 😅\n"
        "🌐 /tr &lt;lang&gt; — translate, bhasha ki koi dikkat nahi 🗣️\n"
        "⚖️ /appeal — ban appeal (DM me), second chance 🙏\n\n"
        "👑 <b>Owner Only:</b> <i>(sirf owner, baaki log hasenge)</i>\n"
        "👑 /backup — pura data backup, safe side 💾\n"
        "👑 /restore — wapas lao, kuch nahi bhoola\n"
        "👑 /gban — global ban, tumhara order sab jagah ⚡\n"
        "👑 /ungban — maaf kar do, global wali maafi\n"
        "👑 /gbans — global ban list\n"
        "👑 /removelogchannel — log channel hatao"
    ),
}

HELP_BTNS = InlineKeyboardMarkup([
    [InlineKeyboardButton("🟢 Basic", callback_data="help:basic"),
     InlineKeyboardButton("🟡 Medium", callback_data="help:medium"),
     InlineKeyboardButton("🔴 Advanced", callback_data="help:advanced")],
    [InlineKeyboardButton("🔙 Close", callback_data="help:close")],
])


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Basic", callback_data="help:basic"),
         InlineKeyboardButton("🟡 Medium", callback_data="help:medium")],
        [InlineKeyboardButton("🔴 Advanced", callback_data="help:advanced")],
        [InlineKeyboardButton("🔙 Close", callback_data="help:close")],
    ])
    await update.message.reply_text(
        "🗂️ <b>Command Help</b> — layer choose karo:",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def on_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    page = query.data.split(":")[1]
    text = HELP_PAGES.get(page, HELP_PAGES["basic"])
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 Basic", callback_data="help:basic"),
         InlineKeyboardButton("🟡 Medium", callback_data="help:medium")],
        [InlineKeyboardButton("🔴 Advanced", callback_data="help:advanced")],
        [InlineKeyboardButton("🔙 Close", callback_data="help:close")],
    ])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


async def on_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    new_members = update.effective_message.new_chat_members

    # 1. Raid check (check_raid khud saare naye members log karta hai)
    if await raid.check_raid(update, context):
        return

    # 2. Captcha — mode ke hisaab se
    mode = store.get_captcha_mode(chat.id)
    if mode in ("button", "image"):
        for member in new_members:
            if member.is_bot:
                continue
            await captchaplus._restrict_and_send_captcha(
                context, chat.id, member.id, member.mention_html()
            )
    else:
        # math mode — captcha.on_new_member khud pura update process karta hai
        await captcha.on_new_member(update, context)


async def on_bot_membership_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member = update.my_chat_member
    if not chat_member:
        return
    new_status = chat_member.new_chat_member.status
    chat = update.effective_chat
    if new_status in ("left", "kicked"):
        db.remove_group(chat.id)
    elif new_status in ("member", "administrator"):
        db.track_group(chat.id, chat.title or "Group")


async def on_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner Panel broadcast capture."""
    await panel.handle_broadcast_message(update, context)

    if await fun.on_confession_text(update, context):
        return
    await panel.handle_broadcast_message(update, context)


async def on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passive counter for /stats."""
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        db.increment_command_count(update.effective_chat.id)


async def on_error(update, context):
    """Global error handler — saare unhandled errors Errors panel me jayenge."""
    logger.error("Update me error aaya: %s", context.error, exc_info=context.error)


async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Full passive pipeline — har normal group text message pe."""
    user = update.effective_user
    chat = update.effective_chat
    msg = update.effective_message
    if not user or not chat or not msg or user.is_bot:
        return

    if await fun.on_count_message(update, context):
        return

    # Group registry + seen users (/tagall aur panel ke liye)
    db.track_group(chat.id, chat.title or "Group")
    db.track_user(chat.id, user.id, user.username or "", user.first_name or "")
    db.increment_message_count(chat.id)

    # Activity tracking (/activity chart ke liye)
    store.bump_activity(chat.id, user.id)

    # Autoreact — bot random reaction lagata hai (consume nahi karta)
    await autoreact.on_autoreact(update, context)

    # Image captcha answer check
    if await captchaplus.on_image_captcha_text(update, context):
        return

    # Global ban check
    if await gban.on_gban_check(update, context):
        return

    # Spam score check
    if await spamscore.check_message(update, context):
        return

    # Global blocklist (gaali/scam words — hamesha on, koi exempt nahi)
    if await blocklist.check_blocklist(update, context):
        return

    # Anti-forward check
    if await antiforward.check_forward(update, context):
        return

    # Raid ke baad wala soft slow-mode (fast messages delete)
    if await raid.enforce_slowmode(update, context):
        return

    # Anti-spam / flood control
    await antispam.check_flood(update, context)

    # Word filters / link block
    await filters_handler.check_filters(update, context)
    await content_filter.check_links(update, context)

    # #hashtag notes — /save se bane notes trigger hote hain yahan
    await notes.check_note_trigger(update, context)

    # Auto-responses
    await autoresponses.check_auto_response(update, context)

    # XP system
    db.add_xp(chat.id, user.id, random.randint(XP_MIN_PER_MESSAGE, XP_MAX_PER_MESSAGE),
              XP_COOLDOWN_SECONDS)


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN environment variable set nahi hai!")

    db.init_db()
    keep_alive()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("setleave", welcome.cmd_setleave))
    app.add_handler(CallbackQueryHandler(on_help_callback, pattern=r"^help:"))
    app.add_handler(CallbackQueryHandler(settings_panel.on_settings_callback, pattern=r"^setpnl:"))
    app.add_handler(CommandHandler("sethelp", settings_panel.cmd_sethelp))

    # Basic
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_error_handler(on_error)
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("info", info.cmd_info))
    app.add_handler(CommandHandler("stats", stats.cmd_stats))

    # Admin+
    app.add_handler(CommandHandler("purge", adminplus.cmd_purge))
    app.add_handler(CommandHandler("report", adminplus.cmd_report))
    app.add_handler(CommandHandler("status", adminplus.cmd_status))

    # Moderation
    app.add_handler(CommandHandler("mute", moderation.cmd_mute))
    app.add_handler(CommandHandler("unmute", moderation.cmd_unmute))
    app.add_handler(CommandHandler("ban", moderation.cmd_ban))
    app.add_handler(CommandHandler("unban", moderation.cmd_unban))
    app.add_handler(CommandHandler("kick", moderation.cmd_kick))
    app.add_handler(CommandHandler("warn", moderation.cmd_warn))
    app.add_handler(CommandHandler("unwarn", moderation.cmd_unwarn))
    app.add_handler(CommandHandler("warnings", moderation.cmd_warnings))

    # Filters
    app.add_handler(CommandHandler("addfilter", filters_handler.cmd_addfilter))
    app.add_handler(CommandHandler("removefilter", filters_handler.cmd_removefilter))
    app.add_handler(CommandHandler("filters", filters_handler.cmd_filters))

    # Link / media / raid protection
    app.add_handler(CommandHandler("setlinkblock", content_filter.cmd_setlinkblock))
    app.add_handler(CommandHandler("restrictmedia", content_filter.cmd_restrictmedia))
    app.add_handler(CommandHandler("raidprotection", raid.cmd_raidprotection))
    app.add_handler(CommandHandler("setraidlimits", raid.cmd_setraidlimits))
    app.add_handler(CommandHandler("lock", raid.cmd_lock))
    app.add_handler(CommandHandler("unlock", raid.cmd_unlock))

    # Admin log channel
    app.add_handler(CommandHandler("setlogchannel", logs.cmd_setlogchannel))
    app.add_handler(CommandHandler("removelogchannel", logs.cmd_removelogchannel))

    # Night mode
    app.add_handler(CommandHandler("nightmode", nightmode.cmd_nightmode))
    app.add_handler(CommandHandler("setnighttime", nightmode.cmd_setnighttime))

    # Welcome + rules gate
    app.add_handler(CommandHandler("setwelcome", welcome.cmd_setwelcome))
    app.add_handler(CommandHandler("setrules", rules.cmd_setrules))
    app.add_handler(CommandHandler("rules", rules.cmd_rules))
    app.add_handler(CommandHandler("rulesgate", rules.cmd_rulesgate))
    app.add_handler(CommandHandler("autodeletejoinleave", joinleave.cmd_autodeletejoinleave))

    # Auto-pin, tag-all
    app.add_handler(CommandHandler("autopin", autopin.cmd_autopin))
    app.add_handler(CommandHandler("tagall", tagall.cmd_tagall))
    app.add_handler(CommandHandler("all", tagall.cmd_tagall))

    # Notes
    app.add_handler(CommandHandler("save", notes.cmd_save))
    app.add_handler(CommandHandler("clear", notes.cmd_clear))
    app.add_handler(CommandHandler("notes", notes.cmd_notes))

    # Auto-responses
    app.add_handler(CommandHandler("addresponse", autoresponses.cmd_addresponse))
    app.add_handler(CommandHandler("delresponse", autoresponses.cmd_delresponse))
    app.add_handler(CommandHandler("responses", autoresponses.cmd_responses))

    # Pomodoro / reminders / dictionary / xp / polls
    app.add_handler(CommandHandler("pomodoro", pomodoro.cmd_pomodoro))
    app.add_handler(CommandHandler("pomodorostop", pomodoro.cmd_pomodorostop))
    app.add_handler(CommandHandler("remindme", reminders.cmd_remindme))
    app.add_handler(CommandHandler("define", dictionary.cmd_define))
    app.add_handler(CommandHandler("rank", xp.cmd_rank))
    app.add_handler(CommandHandler("leaderboard", xp.cmd_leaderboard))
    app.add_handler(CommandHandler("poll", polls.cmd_poll))
    app.add_handler(CommandHandler("quiz", polls.cmd_quiz))

    # ===== NAYE COMMANDS =====
    app.add_handler(CommandHandler("setcaptchamode", captchaplus.cmd_setcaptchamode))
    app.add_handler(CommandHandler("appeal", appeals.cmd_appeal))
    app.add_handler(CommandHandler("backup", backup.cmd_backup))
    app.add_handler(CommandHandler("restore", backup.cmd_restore))
    app.add_handler(CommandHandler("invites", invites.cmd_invites))
    app.add_handler(CommandHandler("invitetop", invites.cmd_invitetop))
    app.add_handler(CommandHandler("setwmedia", welcomemedia.cmd_setwmedia))
    app.add_handler(CommandHandler("setwbtn", welcomemedia.cmd_setwbtn))
    app.add_handler(CommandHandler("clearwmedia", welcomemedia.cmd_clearwmedia))
    app.add_handler(CommandHandler("clearwbtn", welcomemedia.cmd_clearwbtn))
    app.add_handler(CommandHandler("tr", translate.cmd_tr))
    app.add_handler(CommandHandler("alias", aliases.cmd_alias))
    app.add_handler(CommandHandler("unalias", aliases.cmd_unalias))
    app.add_handler(CommandHandler("aliases", aliases.cmd_aliases))
    app.add_handler(CommandHandler("schedule", scheduler.cmd_schedule))
    app.add_handler(CommandHandler("scheduled", scheduler.cmd_scheduled))
    app.add_handler(CommandHandler("unsched", scheduler.cmd_unsched))
    app.add_handler(CommandHandler("approve", approve.cmd_approve))
    app.add_handler(CommandHandler("unapprove", approve.cmd_unapprove))
    app.add_handler(CommandHandler("approved", approve.cmd_approved))
    app.add_handler(CommandHandler("activity", activity.cmd_activity))
    app.add_handler(CommandHandler("gban", gban.cmd_gban))
    app.add_handler(CommandHandler("ungban", gban.cmd_ungban))
    app.add_handler(CommandHandler("gbans", gban.cmd_gbans))
    app.add_handler(CommandHandler("antiforward", antiforward.cmd_antiforward))
    app.add_handler(CommandHandler("checkperms", security.cmd_checkperms))
    app.add_handler(CommandHandler("allowdomain", security.cmd_allowdomain))
    app.add_handler(CommandHandler("removedomain", security.cmd_removedomain))
    app.add_handler(CommandHandler("alloweddomains", security.cmd_alloweddomains))
    app.add_handler(CommandHandler("securitystatus", security.cmd_securitystatus))
    app.add_handler(CommandHandler("quarantine", security.cmd_quarantine))
    app.add_handler(CommandHandler("weather", extra2.cmd_weather))
    app.add_handler(CommandHandler("wiki", extra2.cmd_wiki))
    app.add_handler(CommandHandler("qr", extra2.cmd_qr))
    app.add_handler(CommandHandler("calc", extra2.cmd_calc))
    app.add_handler(CommandHandler("time", extra2.cmd_time))
    app.add_handler(CommandHandler("shorturl", extra2.cmd_shorturl))
    app.add_handler(CommandHandler("guess", extra2.cmd_guess))
    app.add_handler(CommandHandler("smart", smartreply.cmd_smart))
    app.add_handler(CommandHandler("unsmart", smartreply.cmd_unsmart))
    app.add_handler(CommandHandler("smartlist", smartreply.cmd_smartlist))
    app.add_handler(CommandHandler("pro", smartreply.cmd_pro))
    app.add_handler(CommandHandler("play", music.cmd_play))
    app.add_handler(CommandHandler("pause", music.cmd_pause))
    app.add_handler(CommandHandler("resume", music.cmd_resume))
    app.add_handler(CommandHandler("next", music.cmd_next))
    app.add_handler(CommandHandler("previous", music.cmd_previous))
    app.add_handler(CommandHandler("np", music.cmd_np))
    app.add_handler(CommandHandler("queue", music.cmd_queue))
    app.add_handler(CallbackQueryHandler(music.on_music_button, pattern=r"^mus:"))
    app.add_handler(CommandHandler("roast", fun.cmd_roast))
    app.add_handler(CommandHandler("compliment", fun.cmd_compliment))
    app.add_handler(CommandHandler("fortune", fun.cmd_fortune))
    app.add_handler(CommandHandler("ticket", fun.cmd_ticket))
    app.add_handler(CommandHandler("count", fun.cmd_count))
    app.add_handler(CommandHandler("countstop", fun.cmd_countstop))
    app.add_handler(CommandHandler("rep", fun.cmd_rep))
    app.add_handler(CommandHandler("emojistory", fun.cmd_emojistory))
    app.add_handler(CommandHandler("emojistorywin", fun.cmd_emojistorywin))
    app.add_handler(CommandHandler("pet", fun.cmd_pet))
    app.add_handler(CommandHandler("feed", fun.cmd_feed))
    app.add_handler(CommandHandler("feed", fun.cmd_feed))
    app.add_handler(CommandHandler("petplay", fun.cmd_play))
    app.add_handler(CommandHandler("confess", fun.cmd_confess))
    app.add_handler(CommandHandler("autoreact", autoreact.cmd_autoreact))


    # ===== NAYE CALLBACKS =====
    app.add_handler(CallbackQueryHandler(captchaplus.on_captcha_plus_answer, pattern=r"^captchaplus:"))
    app.add_handler(CallbackQueryHandler(appeals.on_appeal_callback, pattern=r"^appeal:"))

    # Invite join requests
    app.add_handler(ChatJoinRequestHandler(invites.on_join_request))

    # ===== NAYE PASSIVE HANDLERS (alag groups — ek doosre ko block na karein) =====
    # Security+: media spam + night hardening + quarantine (photo/gif/video/sticker/voice)
    app.add_handler(MessageHandler(
        (~filters.TEXT & ~filters.COMMAND) & filters.ChatType.GROUPS,
        security.on_media
    ), group=3)

    # Security+: malicious files
    app.add_handler(MessageHandler(
        filters.Document.ALL & filters.ChatType.GROUPS,
        security.on_document
    ), group=3)

    # Security+: URL whitelist (text messages)
    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND,
        security.check_url_whitelist
    ), group=3)

    # Security+: naye members (bot-detection, sus name, join pattern, quarantine tracking)
    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        security.on_new_member
    ), group=2)

    # Security+: demotion alert
    app.add_handler(ChatMemberHandler(
        security.on_my_membership, ChatMemberHandler.MY_CHAT_MEMBER
    ), group=3)
    
    # Channel-spam: auto-forwarded channel posts delete + mute
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND,
        channelspam.on_group_message
    ), group=2)

    # Anti-edit spam: edited messages ka spam check
    app.add_handler(MessageHandler(
        filters.UpdateType.EDITED_MESSAGE & filters.ChatType.GROUPS,
        antiedit.on_edited
    ), group=4)

    # Alias resolve: sabse pehle chalna chahiye
    app.add_handler(MessageHandler(
        filters.COMMAND & filters.ChatType.GROUPS,
        aliases.resolve_alias
    ), group=-1)

    # Welcome media: naye members ko media welcome
    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        welcomemedia.on_new_member
    ), group=1)

    # Passive command counter for /stats
    app.add_handler(MessageHandler(
        filters.COMMAND & filters.ChatType.GROUPS, on_command
    ), group=5)

    # Smart auto-reply: har group text message pe keyword check
    app.add_handler(
        MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, smartreply.check_smart_reply),
        group=6,
    )

    # New member pipeline: raid check -> captcha
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_chat_members))
    app.add_handler(CallbackQueryHandler(captcha.on_captcha_answer, pattern=r"^captcha:"))
    app.add_handler(CallbackQueryHandler(rules.on_rules_accept, pattern=r"^rules:"))

    # /start control panel
    app.add_handler(CallbackQueryHandler(panel.on_panel_callback, pattern=r"^pnl:"))
    app.add_handler(ChatMemberHandler(on_bot_membership_change, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(
        MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, on_private_text)
    )

    # Join/leave service message cleanup
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER,
            joinleave.on_join_leave_service_message,
        ),
        group=1,
    )

    # Full passive pipeline — har normal group text message
    app.add_handler(
        MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, on_group_message)
    )

    # Restart-proof schedules: night mode + scheduled messages
    schedule_startup_jobs(app)

    # Hourly XP leaderboard auto-post (har group me)
    app.job_queue.run_repeating(
        xp.post_hourly_leaderboards,
        interval=LEADERBOARD_INTERVAL_MINUTES * 60,
        first=LEADERBOARD_INTERVAL_MINUTES * 60,
    )

    logger.info("%s starting... %s", BOT_NAME, BOT_CREDIT)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


def schedule_startup_jobs(app: Application):
    nightmode.schedule_all_night_modes(app)
    scheduler.rearm_schedules(app)


if __name__ == "__main__":
    main()
