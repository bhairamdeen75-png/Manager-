import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)
from handlers import adminplus
from config import BOT_TOKEN, BOT_NAME, BOT_CREDIT
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


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"🗂️ <b>{BOT_NAME} — Command List</b>\n"
        f"<i>{BOT_CREDIT}</i>\n\n"
        "🕵️ <b>/start</b> — control panel kholo (my groups, settings, owner panel)\n"
        "🕵️ <b>/help</b> — ye list dobara dekho\n\n"
        "👮 <b>Moderation</b> <i>(kisi user ke message pe reply karke use karo)</i>\n"
        "👮 /mute [minutes] — user ko chup karao\n"
        "👮 /unmute — bolne do wapas\n"
        "👮 /ban — group se hamesha ke liye nikalo\n"
        "👮 /unban &lt;user_id&gt; — rejoin allow karo\n"
        "👮 /kick — nikalo, rejoin kar sakta hai\n"
        "👮 /warn · /unwarn · /warnings — warning system\n"
        "👮 /info — reply kiye gaye user ki full profile\n\n"
        "🛡️ <b>Filters &amp; Protection</b>\n"
        "🛡️ /addfilter, /removefilter, /filters — banned words\n"
        "🛡️ /setlinkblock on|off — links/usernames auto-block\n"
        "🛡️ /restrictmedia &lt;types|all|none&gt;\n"
        "🛡️ /raidprotection on|off · /setraidlimits &lt;joins&gt; &lt;secs&gt; &lt;lock_min&gt;\n"
        "🛡️ /lock · /unlock — group manually lock/unlock\n\n"
        "📜 <b>Welcome &amp; Rules</b>\n"
        "📜 /setwelcome &lt;text&gt;\n"
        "📜 /setrules &lt;text&gt; · /rules · /rulesgate on|off\n"
        "📜 /autodeletejoinleave on|off\n\n"
        "✨ <b>Group Vibe</b>\n"
        "✨ /nightmode on|off · /setnighttime HH:MM HH:MM (UTC)\n"
        "✨ /autopin on|off · /tagall &lt;reason&gt;\n\n"
        "📝 <b>Notes &amp; Auto-Responses</b>\n"
        "📝 /save &lt;name&gt; &lt;text&gt; · /notes · /clear &lt;name&gt; — trigger with #name\n"
        "📝 /addresponse trigger | response · /delresponse · /responses\n\n"
        "🎉 <b>Fun &amp; Utility</b>\n"
        "🎉 /poll Q | opt1 | opt2 · /quiz Q | correct_index | opt1 | opt2\n"
        "🎉 /pomodoro &lt;work_min&gt; &lt;break_min&gt; [cycles] · /pomodorostop\n"
        "🎉 /remindme &lt;10m|2h|1d&gt; &lt;text&gt; · /define &lt;word&gt;\n"
        "🎉 /rank · /leaderboard\n\n"
        "📊 <b>Admin Log &amp; Stats</b>\n"
        "📊 /setlogchannel &lt;channel_id&gt; · /removelogchannel · /stats\n\n"
        "Tip: <b>/start</b> bhejo aur buttons se sab kuch bina typing ke manage karo 😉"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Runs the full passive pipeline on every normal group text message."""
    # Hard checks that can delete the message — run these first.
    if await raid.enforce_slowmode(update, context):
        return
    if await content_filter.check_links(update, context):
        return
    if await content_filter.check_media(update, context):
        return
    await filters_handler.check_filters(update, context)
    await antispam.check_flood(update, context)

    # Passive/background bookkeeping — safe to run even if the message above
    # was already handled, since check_filters/check_flood self-guard.
    db.track_group(update.effective_chat.id, update.effective_chat.title or "Group")
    db.increment_message_count(update.effective_chat.id)
    await joinleave.track_seen_user(update, context)
    await xp.award_xp(update, context)
    await autopin.maybe_autopin(update, context)
    await notes.check_note_trigger(update, context)
    await autoresponses.check_auto_response(update, context)


async def on_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_id = context.bot.id
    new_members = update.effective_message.new_chat_members
    chat = update.effective_chat

    logger.info("JOIN EVENT: chat=%s (%s) members=%s", chat.id, chat.title, [m.id for m in new_members])

    if any(m.id == bot_id for m in new_members):
        db.track_group(chat.id, chat.title or "Group")
        await update.effective_message.reply_text(
            f"👋 Dhanyavaad group me add karne ke liye! Main <b>{BOT_NAME}</b> hoon.\n\n"
            "Mujhe admin banao (delete/ban/restrict/pin rights ke saath) taaki sab features kaam karein.\n"
            "/help se commands dekho, ya DM me /start se control panel kholo.",
            parse_mode="HTML",
        )
        return

    try:
        raided = await raid.check_raid(update, context)
        if raided:
            return
command executed
        # Rules gate crash hone par captcha zaroor chale — isliye alag try me
        try:
            await rules.on_new_member_rules_gate(update, context)
        except Exception:
            logger.exception("Rules gate failed for chat %s", chat.id)

        await captcha.on_new_member(update, context)
    except Exception:
        logger.exception("Join pipeline failed for chat %s", chat.id)

    raided = await raid.check_raid(update, context)
    if raided:
        return
    await rules.on_new_member_rules_gate(update, context)
    await captcha.on_new_member(update, context)


async def on_bot_membership_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Keeps the groups registry accurate when the bot is kicked/removed or
    leaves a group, so the owner panel and 'My Groups' stay correct."""
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
    """Captures the owner's next message after tapping 'Broadcast' in the
    Owner Panel. No-op for everyone else / when no broadcast is pending."""
    await panel.handle_broadcast_message(update, context)


async def on_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Passive counter for /stats — runs alongside the real command handlers."""
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        db.increment_command_count(update.effective_chat.id)


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN environment variable set nahi hai!")

    db.init_db()
    keep_alive()  # start Flask server so Render web-service stays reachable

    app = Application.builder().token(BOT_TOKEN).build()

    # Basic
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("info", info.cmd_info))
    app.add_handler(CommandHandler("stats", cmd_stats ...))

    # Admin+                                          ✅ SAHI JAGAH
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

    # Passive command counter for /stats (own group so it never blocks real commands)
    app.add_handler(MessageHandler(filters.COMMAND & filters.ChatType.GROUPS, on_command), group=5)

    # New member pipeline: raid check -> rules gate -> captcha (all in one callback
    # so raid protection can short-circuit the rest during an active raid)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_chat_members))
    app.add_handler(CallbackQueryHandler(captcha.on_captcha_answer, pattern=r"^captcha:"))
    app.add_handler(CallbackQueryHandler(rules.on_rules_accept, pattern=r"^rules:"))

    # /start control panel: My Groups, Group Settings, Owner Panel
    app.add_handler(CallbackQueryHandler(panel.on_panel_callback, pattern=r"^pnl:"))
    app.add_handler(ChatMemberHandler(on_bot_membership_change, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(
        MessageHandler(filters.TEXT & filters.ChatType.PRIVATE & ~filters.COMMAND, on_private_text)
    )

    # Join/leave service message cleanup (own group so it always runs alongside the above)
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS | filters.StatusUpdate.LEFT_CHAT_MEMBER,
            joinleave.on_join_leave_service_message,
        ),
        group=1,
    )

    # Full passive pipeline (filters, anti-spam, links, media, notes, XP, etc.)
    # on every normal group text message
    app.add_handler(
        MessageHandler(filters.TEXT & filters.ChatType.GROUPS & ~filters.COMMAND, on_group_message)
    )

    # Re-arm night mode schedules for groups that had it enabled before a restart
    schedule_startup_jobs(app)

    logger.info("%s starting... %s", BOT_NAME, BOT_CREDIT)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


def schedule_startup_jobs(app: Application):
    nightmode.schedule_all_night_modes(app)


if __name__ == "__main__":
    main()
