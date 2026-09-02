"""/alias chup mute → ab /chup /mute jaisa chalega. /aliases list, /unalias hatao."""

import logging

from telegram import MessageEntity, Update
from telegram.ext import ContextTypes, MessageHandler, filters

import database as db
from handlers import store
from handlers.utils import is_admin

logger = logging.getLogger(__name__)


async def cmd_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Format: /alias <short> <realcommand>\nJaise: /alias chup mute")
        return
    alias, target = context.args[0], context.args[1]
    store.set_alias(update.effective_chat.id, alias, target)
    await update.message.reply_text(f"✅ Ab /{alias} == /{target}")


async def cmd_unalias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("Format: /unalias <short>")
        return
    store.del_alias(update.effective_chat.id, context.args[0])
    await update.message.reply_text("🧹 Alias hata diya.")


async def cmd_aliases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amap = store.get_aliases(update.effective_chat.id)
    if not amap:
        await update.message.reply_text("Koi alias nahi hai. /alias se banao.")
        return
    lines = ["🔗 **Aliases:**"] + [f"/{a} → /{t}" for a, t in sorted(amap.items())]
    await update.message.reply_text("\n".join(lines))


async def resolve_alias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """group=-1 me registered — sabse pehle chalta hai. Alias ko real command me badal ke
    update dobara process karta hai. Chain resolve karta hai (a→b→real)."""
    msg = update.effective_message
    if not msg or not msg.text or not msg.entities:
        return
    first = msg.entities[0]
    if first.type != MessageEntity.BOT_COMMAND or first.offset != 0:
        return
    cmd = msg.text[1:first.length].split("@")[0].lower()
    amap = store.get_aliases(update.effective_chat.id)
    if cmd not in amap:
        return
    # Chain resolve (max 5, loop protection)
    target = amap[cmd]
    for _ in range(5):
        if target in amap:
            target = amap[target]
        else:
            break
    if target in amap:
        return  # infinite chain — bail
    new_cmd = "/" + target
    rest = msg.text[first.length:]  # arguments
    new_text = new_cmd + rest
    try:
        msg.text = new_text
        if msg.entities:
            ents = list(msg.entities)
            ents[0] = MessageEntity(type=MessageEntity.BOT_COMMAND, offset=0, length=len(new_cmd))
            msg.entities = ents
        await context.application.process_update(update)
    except Exception as e:
        logger.warning("Alias dispatch fail: %s", e)
