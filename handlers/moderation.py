from datetime import timedelta

from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes

import database as db
from config import MAX_WARNS
from handlers.utils import is_admin, get_target_user


def _parse_minutes(args, default=0):
    if args:
        try:
            return int(args[0])
        except ValueError:
            return default
    return default


async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    target = get_target_user(update)
    if not target:
        await update.message.reply_text("Kisi user ke message pe reply karke /mute [minutes] likho.")
        return

    minutes = _parse_minutes(context.args)
    until = None
    if minutes > 0:
        from datetime import datetime, timezone
        until = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        target.id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=until,
    )
    label = f"{minutes} minute(s)" if minutes > 0 else "hamesha ke liye"
    await update.message.reply_text(f"🔇 {target.mention_html()} ko {label} mute kar diya.", parse_mode="HTML")


async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    target = get_target_user(update)
    if not target:
        await update.message.reply_text("Kisi user ke message pe reply karke /unmute likho.")
        return

    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        target.id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
        ),
    )
    await update.message.reply_text(f"🔊 {target.mention_html()} ko unmute kar diya.", parse_mode="HTML")


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    target = get_target_user(update)
    if not target:
        await update.message.reply_text("Kisi user ke message pe reply karke /ban likho.")
        return
    await context.bot.ban_chat_member(update.effective_chat.id, target.id)
    await update.message.reply_text(f"⛔ {target.mention_html()} ko ban kar diya.", parse_mode="HTML")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args:
        await update.message.reply_text("Use karo: /unban <user_id>")
        return
    try:
        user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Valid user_id do.")
        return
    await context.bot.unban_chat_member(update.effective_chat.id, user_id)
    await update.message.reply_text("✅ User unban ho gaya.")


async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    target = get_target_user(update)
    if not target:
        await update.message.reply_text("Kisi user ke message pe reply karke /kick likho.")
        return
    chat_id = update.effective_chat.id
    await context.bot.ban_chat_member(chat_id, target.id)
    await context.bot.unban_chat_member(chat_id, target.id)
    await update.message.reply_text(f"👢 {target.mention_html()} ko kick kar diya.", parse_mode="HTML")


async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    target = get_target_user(update)
    if not target:
        await update.message.reply_text("Kisi user ke message pe reply karke /warn likho.")
        return

    chat_id = update.effective_chat.id
    count = db.add_warn(chat_id, target.id)

    if count >= MAX_WARNS:
        db.reset_warns(chat_id, target.id)
        await context.bot.ban_chat_member(chat_id, target.id)
        await update.message.reply_text(
            f"⛔ {target.mention_html()} ne {MAX_WARNS} warnings paar kar di — ban kar diya gaya.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"⚠️ {target.mention_html()} ko warn kiya gaya. ({count}/{MAX_WARNS})",
            parse_mode="HTML",
        )


async def cmd_unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    target = get_target_user(update)
    if not target:
        await update.message.reply_text("Kisi user ke message pe reply karke /unwarn likho.")
        return
    db.reset_warns(update.effective_chat.id, target.id)
    await update.message.reply_text(f"✅ {target.mention_html()} ke warnings clear kar diye.", parse_mode="HTML")


async def cmd_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = get_target_user(update) or update.effective_user
    count = db.get_warns(update.effective_chat.id, target.id)
    await update.message.reply_text(f"{target.mention_html()} ke pass {count}/{MAX_WARNS} warnings hain.", parse_mode="HTML")
