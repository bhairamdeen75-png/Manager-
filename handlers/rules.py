from telegram import (
    Update,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

import database as db
from handlers.utils import is_admin

DEFAULT_RULES = "Is group ke koi specific rules set nahi hain. Respectful raho aur spam mat karo."

_UNMUTED_PERMISSIONS = ChatPermissions(
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
)

# pending[(chat_id, user_id)] = True while user hasn't accepted rules yet
_pending: dict[tuple[int, int], bool] = {}


async def cmd_setrules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args:
        await update.message.reply_text("Use karo: /setrules <rules text>")
        return
    text = " ".join(context.args)
    db.set_rules(update.effective_chat.id, text)
    await update.message.reply_text("✅ Group rules set ho gaye.")


async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = db.get_rules(update.effective_chat.id) or DEFAULT_RULES
    await update.message.reply_text(f"📜 <b>Group Rules</b>\n\n{text}", parse_mode="HTML")


async def cmd_rulesgate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/rulesgate on|off — naye members ko rules accept karne tak muted rakho."""
    if not await is_admin(update, context):
        await update.message.reply_text("Sirf admins hi ye command use kar sakte hain.")
        return
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Use karo: /rulesgate on|off")
        return
    enabled = context.args[0].lower() == "on"
    db.set_rules_gate(update.effective_chat.id, enabled)
    state = "ON ✅" if enabled else "OFF ❌"
    await update.message.reply_text(f"📜 Rules-accept gate: {state}")


async def on_new_member_rules_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Runs alongside captcha for every new member if rules_gate is enabled."""
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return
    if not db.get_rules_gate(chat.id):
        return

    rules_text = db.get_rules(chat.id) or DEFAULT_RULES

    for member in update.effective_message.new_chat_members:
        if member.is_bot:
            continue
        key = (chat.id, member.id)
        _pending[key] = True

        try:
            await context.bot.restrict_chat_member(
                chat.id, member.id, permissions=ChatPermissions(can_send_messages=False)
            )
        except Exception:
            pass

        button = InlineKeyboardButton("✅ I Accept the Rules", callback_data=f"rules:{chat.id}:{member.id}")
        await context.bot.send_message(
            chat.id,
            f"📜 {member.mention_html()}, group me likhne se pehle rules accept karo:\n\n{rules_text}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[button]]),
        )


async def on_rules_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, chat_id, user_id = query.data.split(":")
    chat_id, user_id = int(chat_id), int(user_id)
    key = (chat_id, user_id)

    if query.from_user.id != user_id:
        await query.answer("Ye button tumhare liye nahi hai.", show_alert=True)
        return

    if key not in _pending:
        await query.answer("Ye request expire ho chuki hai.", show_alert=True)
        return

    del _pending[key]
    try:
        await context.bot.restrict_chat_member(chat_id, user_id, permissions=_UNMUTED_PERMISSIONS)
    except Exception:
        pass

    await query.edit_message_text("✅ Rules accept ho gaye. Ab tum message bhej sakte ho — welcome!")
    await query.answer("Accepted!")
