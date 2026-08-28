import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

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
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 Namaste! Main <b>{BOT_NAME}</b> hoon — tumhara group management bot.\n\n"
        "Features: anti-spam, raid protection, link/scam filter, media restriction, "
        "notes, auto-responses, XP+leaderboard, polls/quiz, reminders, pomodoro aur bahut kuch.\n\n"
        "Mujhe group me admin banao (delete/ban/restrict rights ke saath) "
        "aur /help se commands dekho.\n\n"
        f"{BOT_CREDIT}",
        parse_mode="HTML",
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"<b>📋 {BOT_NAME} — Commands</b>\n\n"
        "<b>Moderation (reply to a user's message):</b>\n"
        "/mute [minutes] · /unmute · /ban · /unban &lt;user_id&gt; · /kick\n"
        "/warn · /unwarn · /warnings · /info\n\n"
        "<b>Filters &amp; protection:</b>\n"
        "/addfilter &lt;word&gt; · /removefilter &lt;word&gt; · /filters\n"
        "/setlinkblock on|off — links/usernames/obfuscated links block karo\n"
        "/restrictmedia &lt;types|all|none&gt;\n"
        "/raidprotection on|off · /setraidlimits &lt;joins&gt; &lt;secs&gt; &lt;lock_min&gt;\n"
        "/lock · /unlock — group ko manually lock/unlock karo\n\n"
        "<b>Welcome &amp; rules:</b>\n"
        "/setwelcome &lt;text&gt;\n"
        "/setrules &lt;text&gt; · /rules · /rulesgate on|off\n"
        "/autodeletejoinleave on|off\n\n"
        "<b>Group vibe:</b>\n"
        "/nightmode on|off · /setnighttime HH:MM HH:MM (UTC)\n"
        "/autopin on|off\n"
        "/tagall &lt;reason&gt;\n\n"
        "<b>Notes &amp; auto-responses:</b>\n"
        "/save &lt;name&gt; &lt;text&gt; · /notes · /clear &lt;name&gt; — trigger with #name\n"
        "/addresponse trigger | response · /delresponse &lt;trigger&gt; · /responses\n\n"
        "<b>Fun &amp; utility:</b>\n"
        "/poll Q | opt1 | opt2 · /quiz Q | correct_index | opt1 | opt2\n"
        "/pomodoro &lt;work_min&gt; &lt;break_min&gt; [cycles] · /pomodorostop\n"
        "/remindme &lt;10m|2h|1d&gt; &lt;text&gt;\n"
        "/define &lt;word&gt;\n"
        "/rank · /leaderboard\n\n"
        "<b>Admin log &amp; stats:</b>\n"
        "/setlogchannel &lt;channel_id&gt; · /removelogchannel\n"
        "/stats\n\n"
        f"{BOT_CREDIT}"
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
    db.increment_message_count(update.effective_chat.id)
    await joinleave.track_seen_user(update, context)
    await xp.award_xp(update, context)
    await autopin.maybe_autopin(update, context)
    await notes.check_note_trigger(update, context)
    await autoresponses.check_auto_response(update, context)


async def on_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Single entry point for the new-member pipeline: raid check first (can
    short-circuit everything else during an active raid), then rules gate,
    then captcha."""
    raided = await raid.check_raid(update, context)
    if raided:
        return
    await rules.on_new_member_rules_gate(update, context)
    await captcha.on_new_member(update, context)


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
    app.add_handler(CommandHandler("stats", stats.cmd_stats))

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
