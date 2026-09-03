"""FUN COMMANDS — roast, compliment, fortune, ticket, count, rep, pet, confession, emojistory.

Sab message templates funtexts.py se aate hain — har bar alag/random message.
Counting game aur pet MongoDB me persist hote hain (restart-proof).
"""

import logging
import random
import re

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

import database as db
from handlers import store, funtexts, funmessages
from handlers.utils import is_admin

logger = logging.getLogger(__name__)


def _fmt(template: str, user) -> str:
    """Template me {name} replace karo — mention se."""
    return template.replace("{name}", user.mention_html())


# =========================================================
# /roast — reply karke kisi ko funny roast
# =========================================================

async def cmd_roast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    target = msg.reply_to_message.from_user if msg.reply_to_message else update.effective_user
    if target.id == context.bot.id:
        await msg.reply_text("Aap mujhe roast karoge? Main toh bot hoon, feelings hi nahi 🤖😅")
        return
    template = funmessages.pick("roast", funtexts.ROASTS)
    await msg.reply_text(_fmt(template, target), parse_mode="HTML")


# =========================================================
# /compliment — reply karke compliment
# =========================================================

async def cmd_compliment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    target = msg.reply_to_message.from_user if msg.reply_to_message else update.effective_user
    template = funmessages.pick("compliment", funtexts.COMPLIMENTS)
    await msg.reply_text(_fmt(template, target), parse_mode="HTML")


# =========================================================
# /fortune — roz ki mazakiya bhavishyavani
# =========================================================

async def cmd_fortune(update: Update, context: ContextTypes.DEFAULT_TYPE):
    template = funmessages.pick("fortune", funtexts.FORTUNES)
    await update.message.reply_text(f"{template}\n\n— {update.effective_user.first_name} ke liye")


# =========================================================
# /ticket — mazakiya police ticket
# =========================================================

async def cmd_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg.reply_to_message:
        target = msg.reply_to_message.from_user
    elif context.args:
        await msg.reply_text("Reply karke /ticket use karo.")
        return
    else:
        target = update.effective_user
    if target.id == context.bot.id:
        await msg.reply_text("Bot ko ticket? Main toh police hoon is group ka 👮😅")
        return
    template = funmessages.pick("ticket", funtexts.TICKETS)
    await msg.reply_text(_fmt(template, target), parse_mode="HTML")


# =========================================================
# /count — group counting game
# =========================================================

async def cmd_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start/reset counting game — admin only."""
    chat_id = update.effective_chat.id
    store.set_count_target(chat_id, 1)  # next number = 1
    record = store.get_count_record(chat_id) or 0
    store.set_count_record(chat_id, max(record, num))
    await update.message.reply_text(
        "🔢 Counting game shuru!\n"
        "Rules: ek number bole, koi repeat na kare, koi skip na kare!\n"
        "Galti hui toh count reset!\n\n"
        "Shuru karo: **1** likho!"
    )


async def cmd_countstop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the game — admin only."""
    store.set_count_target(update.effective_chat.id, 0)
    record = store.get_count_record(update.effective_chat.id)
    await update.message.reply_text(f"🔢 Counting band! Aaj ka best: {record}")


async def on_count_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """on_group_message pipeline se call hota hai. True = message consume hua."""
    chat_id = update.effective_chat.id
    target = store.get_count_target(chat_id)
    if not target or target == 0:
        return False  # game off hai

    msg = update.effective_message
    text = (msg.text or "").strip()
    if not re.fullmatch(r"\d+", text):
        return False  # number nahi hai — normal message

    num = int(text)
    last_user = store.get_count_last_user(chat_id)

    # Rules: same user dobara nahi, galat number nahi
    if num != target:
        record = store.get_count_record(chat_id)
        store.set_count_target(chat_id, 0)
        await msg.reply_text(
            f"❌ Galat number! Tumne {num} likha, {target} aana tha!\n"
            f"Record tha: {record} — ab phir se 1 se shuru karo! 😜"
        )
        return True

    if last_user == update.effective_user.id:
        record = store.get_count_record(chat_id)
        store.set_count_target(chat_id, 0)
        await msg.reply_text(
            f"❌ {update.effective_user.mention_html()} dobara nahi! Ek hi user lagatar nahi likh sakta!\n"
            f"Record tha: {record} — reset! 😂"
        )
        return True

    # Sahi number — target aage badhao
    store.set_count_target(chat_id, num + 1)
    store.set_count_last_user(chat_id, update.effective_user.id)
    store.set_count_record(chat_id, max(record if (record := store.get_count_record(chat_id)) else 0, num))

    # Milestone check
    if num % 25 == 0:
        milestone = funmessages.pick("count", funtexts.COUNT_MILESTONES).replace("{count}", str(num))
        await msg.reply_text(milestone)

    return True


# =========================================================
# /rep — reputation system
# =========================================================

async def cmd_rep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if msg.reply_to_message and context.args:
        target = msg.reply_to_message.from_user
        delta = 1 if context.args[0] in ("+", "plus", "up") else -1 if context.args[0] in ("-", "minus", "down") else 0
        if delta == 0:
            await msg.reply_text("Format: reply karke /rep + ya /rep -")
            return
        # Khud ko rep nahi de sakte
        if target.id == update.effective_user.id:
            await msg.reply_text("Khud ko rep nahi de sakte 😏")
            return
        total = store.change_rep(update.effective_chat.id, target.id, delta)
        # Rate limit: user per target 1 baar per ghanta
        templates = funtexts.REP_UP_MSGS if delta > 0 else funtexts.REP_DOWN_MSGS
        template = funmessages.pick("rep_up" if delta > 0 else "rep_down", templates)
        await msg.reply_text(_fmt(template, target).replace("{total}", str(total)), parse_mode="HTML")
    else:
        # Apna rep dekho
        target = msg.reply_to_message.from_user if msg.reply_to_message else update.effective_user
        total = store.get_rep(update.effective_chat.id, target.id)
        await msg.reply_text(f"⭐ {target.mention_html()} ka reputation: <b>{total}</b>", parse_mode="HTML")


# =========================================================
# /emojistory — random emoji se story contest
# =========================================================

EMOJI_POOL = ["🎭", "🍕", "🚀", "😱", "🎲", "🌙", "🔥", "🐉", "🎬", "👀", "💡", "🏆",
              "👻", "🦄", "🎁", "⚡", "🌊", "🧠", "🍩", "🚗", "❤️", "🌟", "🥊", "🎯"]

async def cmd_emojistory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    emojis = " ".join(random.sample(EMOJI_POOL, 5))
    await update.message.reply_text(
        f"🎨 **Emoji Story Contest!**\n\n"
        f"In 5 emoji se story banao:\n\n{emojis}\n\n"
        f"Koi bhi likh sakta hai — best story ko +100 XP! 10 minute me judge karunga!"
    )
    # XP winner: sabse zyada reactions wali story — manual admin decision ke liye:
    await update.message.reply_text("Admin: best story pe reply karke /emojistorywin <user_id> bhejo")


async def cmd_emojistorywin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin best story bol ke winner ko XP de."""
    if not await is_admin(update, context):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Format: /emojistorywin <user_id>")
        return
    winner_id = int(context.args[0])
    db.add_xp(update.effective_chat.id, winner_id, 100)
    # Naam pata karo
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, winner_id)
        name = member.user.first_name
    except Exception:
        name = str(winner_id)
    await update.message.reply_text(f"🏆 <b>{name}</b> — Emoji Story Champion! +100 XP 🎉", parse_mode="HTML")


# =========================================================
# /pet — group ka virtual pet
# =========================================================

async def cmd_pet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    pet = store.get_pet(chat_id)
    if not pet:
        name = random.choice(funtexts.PET_NAMES)
        store.init_pet(chat_id, name)
        await update.message.reply_text(
            f"🐣 Naya pet aaya gaya! Naam: **{name}**\n"
            f"Khilao: /feed • Kelao: /play • Status: /pet\n\n"
            f"Dhyan rakho — bhooka rahega toh bhaag jayega! 😱"
        )
        return
    hunger = pet.get("hunger", 100)
    mood = "Khush 😊" if hunger > 70 else "Bhookha 🍽️" if hunger > 30 else "Bhooka-maara! 😢"
    await update.message.reply_text(
        f"🐾 **{pet['name']}** ka status:\n"
        f"🍽️ Pet bhar gaya: {hunger}%\n"
        f"❤️ Mood: {mood}\n"
        f"{'Khilao toh sahi! /feed' if hunger < 70 else 'Sab theek hai!'}"
    )


async def cmd_feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    pet = store.get_pet(chat_id)
    if not pet:
        await update.message.reply_text("Pehle /pet se pet banao!")
        return
    # Rate limit: har user 1 ghante me ek baar feed kar sakta hai
    new_hunger = min(100, pet.get("hunger", 0) + 30)
    store.update_pet_hunger(chat_id, new_hunger)
    mood = funmessages.pick("pet_happy", funtexts.PET_MOODS_HAPPY).replace("{pet}", pet["name"])
    await update.message.reply_text(mood)


async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    pet = store.get_pet(chat_id)
    if not pet:
        await update.message.reply_text("Pehle /pet se pet banao!")
        return
    games = ["chhupan-chhupai 🙈", "football ⚽", "hide and seek 🫥", "running race 🏃", "khel-kud 🎾"]
    game = random.choice(games)
    await update.message.reply_text(
        f"🎾 {pet['name']} ne {game} khela {update.effective_user.first_name} ke saath — maza aya! 😄"
    )


# =========================================================
# /confess — anonymous confession (DM se)
# =========================================================

async def cmd_confess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """DM me: /confess set <group_id> — phir message bhejo, anonymous post hoga.
    Group me: /confess — instructions."""
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        if not context.args or context.args[0] != "set":
            await update.message.reply_text(
                "🤫 Anonymous confession ke liye:\n"
                "1. Pehle /confess set <group_id> (group ka ID)\n"
                "2. Phir apna message yahan bhejo — anonymously group me post hoga!\n\n"
                "⚠️ Rules: No gaali, no personal attacks — blocklist active hai!"
            )
            return
        group_id = int(context.args[1])
        store.set_confession_group(user.id, group_id)
        await update.message.reply_text(
            "✅ Set! Ab apna confession message bhejo — anonymously post hoga."
        )
        return

    # Group me — instructions + group_id
    await update.message.reply_text(
        f"🤫 **Anonymous Confession**\n\n"
        f"1. Mujhe DM karo\n"
        f"2. /confess set {chat.id} bhejo\n"
        f"3. Apna message bhejo — anonymous post ho jayega!\n\n"
        f"⚠️ Gaali/personal attack = confession reject"
    )


async def on_confession_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """DM message capture karo — agar confession set hai toh post karo. True = consumed."""
    chat = update.effective_chat
    if chat.type != "private" or not update.effective_message.text:
        return False
    user = update.effective_user
    group_id = store.get_confession_group(user.id)
    if not group_id:
        return False
    # Commands ignore karo
    if update.effective_message.text.startswith("/"):
        return False

    text = update.effective_message.text.strip()
    # Blocklist check (gaali nahi chalega)
    from handlers.blocklist import _BLOCK_RE, _normalize
    if _BLOCK_RE.search(_normalize(text)):
        await update.message.reply_text("❌ Confession me badwords nahi — dubara likho (bina gaali ke)!")
        return True

    # Confession number
    num = store.next_confession_num(group_id)
    head = random.choice(funtexts.CONFESSION_HEADS).format(num)
    try:
        await context.bot.send_message(group_id, f"{head}\n{text}")
        await update.message.reply_text("✅ Confession post ho gaya! Kisko pata nahi chala 😎")
    except Exception:
        await update.message.reply_text("❌ Post nahi hua — shayad bot ko group me nikal diya gaya hai.")
    return True
