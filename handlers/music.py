"""handlers/music.py — REAL Music Player (audio file playback + button UI)

/play <song ya YT link> → gaana download karke AUDIO FILE bhejta hai (sach me play hoga)
Buttons: ⏭️ Next ⏹️ Stop 🔀 Shuffle (real), /queue /np bhi
Sources: yt-dlp (YouTube) → fallback JioSaavn (Hindi songs, 320kbps)
Queue MongoDB me — restart-proof.
"""

import asyncio
import logging
import os
import random
import re
import tempfile
import time

import httpx
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import database as db

logger = logging.getLogger(__name__)

_queue_col = db.stats_col.database["music_queue"]
TIMEOUT = 90.0
MAX_DURATION = 900  # 15 min se lambi video skip (movies/podcasts nahi)


def _extract_video_id(text: str):
    m = re.search(
        r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})|^([A-Za-z0-9_-]{11})$",
        text.strip(),
    )
    if m:
        return m.group(1) or m.group(2)
    return None


# ---------------- Track resolve (yt-dlp → JioSaavn fallback) ----------------

def _ydl_resolve(query: str):
    """yt-dlp se track info + audio download karke path return karo."""
    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "noplaylist": True, "quiet": True, "no_warnings": True,
        "default_search": "ytsearch1", "outtmpl": os.path.join(tempfile.gettempdir(), "%(id)s.%(ext)s"),
    }
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(query, download=True)
    if "entries" in info:
        info = info["entries"][0]
    path = os.path.join(tempfile.gettempdir(), f"{info['id']}.{info.get('ext', 'm4a')}")
    return {
        "title": info.get("title", "Unknown"),
        "uploader": info.get("uploader", "Unknown"),
        "duration": info.get("duration", 0),
        "thumbnail": info.get("thumbnail", ""),
        "path": path, "source": "YouTube",
    }


async def _saavn_resolve(query: str):
    """JioSaavn fallback (Hindi gaane, 320kbps, free no-key API)."""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get("https://saavn.dev/api/search/songs", params={"query": query})
            r.raise_for_status()
            results = r.json().get("data", {}).get("results", [])
        if not results:
            return None
        s = results[0]
        urls = s.get("downloadUrl", [])
        url = next((u["link"] for u in reversed(urls) if u.get("link")), None)
        if not url:
            return None
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            fd, path = tempfile.mkstemp(suffix=".mp3")
            with os.fdopen(fd, "wb") as f:
                f.write(r.content)
        return {
            "title": s.get("name", "Unknown"),
            "uploader": (s.get("artists", {}).get("primary") or [{}])[0].get("name", "JioSaavn"),
            "duration": int(s.get("duration", 0) or 0),
            "thumbnail": s.get("image", [{}])[-1].get("link", ""),
            "path": path, "source": "JioSaavn",
        }
    except Exception as e:
        logger.warning("Saavn fail: %s", e)
        return None


async def _resolve_track(query: str):
    """Gaana download karke track dict lao. YouTube pehle, fail → JioSaavn."""
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, _ydl_resolve, query), TIMEOUT)
    except Exception as e:
        logger.warning("yt-dlp fail: %s — JioSaavn try kar raha hu", e)
        return await _saavn_resolve(query)


def _fmt(sec):
    if not sec:
        return "NA"
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def _keyboard(chat_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏮️", callback_data=f"mus:prev:{chat_id}"),
            InlineKeyboardButton("⏭️", callback_data=f"mus:next:{chat_id}"),
            InlineKeyboardButton("🔀 Shuffle", callback_data=f"mus:shuffle:{chat_id}"),
            InlineKeyboardButton("⏹️ Stop", callback_data=f"mus:stop:{chat_id}"),
        ],
    ])


def _get(chat_id):
    doc = _queue_col.find_one({"chat_id": chat_id})
    return doc or {}


def _save(chat_id, tracks, current=None, current_msg_id=None):
    _queue_col.update_one(
        {"chat_id": chat_id},
        {"$set": {"tracks": tracks, "current": current, "current_msg_id": current_msg_id}},
        upsert=True,
    )


async def _send_track(context, chat_id, track, user):
    """Gaana AUDIO FILE ke roop me bhejo — ye SACH ME play hota hai."""
    caption = (
        f"🎧 <b>NOW PLAYING</b>\n\n"
        f"🎵 <b>{track['title']}</b>\n"
        f"👤 <i>{track['uploader']}</i>  •  ⏱️ {_fmt(track['duration'])}  •  {track['source']}\n"
        f"🎤 Requested by: {user}\n\n"
        f"<i>Buttons se control karo — Next dabao to agla gaana khud bajega!</i>"
    )
    with open(track["path"], "rb") as audio:
        msg = await context.bot.send_audio(
            chat_id, audio=audio,
            title=track["title"][:60], performer=track["uploader"][:60],
            caption=caption, parse_mode="HTML", reply_markup=_keyboard(chat_id),
            thumbnail=track["thumbnail"].encode() if track["thumbnail"].startswith("http") else None,
        )
    return msg.message_id


async def _cleanup(path):
    try:
        os.remove(path)
    except Exception:
        pass


# ---------------- /play ----------------

async def cmd_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user.first_name
    query = " ".join(context.args).strip()

    if not query:
        await update.message.reply_text(
            "🎵 <b>PLAY MUSIC</b>\n\n📌 /play <song name ya YouTube link>\n\n"
            "✨ /play kesariya song\n✨ /play https://youtu.be/xyz\n\n"
            "🎮 /next /previous /np /queue",
            parse_mode="HTML",
        )
        return

    status = await update.message.reply_text("🔎 dhundh raha hu... 🎧 download ho raha hai...")
    vid = _extract_video_id(query)
    track = await _resolve_track(vid if vid else query)

    if not track:
        await status.edit_text("😢 Gaana nahi mila bhai! Naam clear likho ya YT link do.")
        return
    if track["duration"] and track["duration"] > MAX_DURATION:
        await status.edit_text("⏱️ Ye bahut lamba hai (15 min+). Sirf gaane chalate hain!")
        await _cleanup(track["path"])
        return

    doc = _get(chat_id)
    tracks = doc.get("tracks", [])
    current = doc.get("current")

    # Agar kuch chal raha hai to purana audio message delete → naya bajao
    if current and doc.get("current_msg_id"):
        try:
            await context.bot.delete_message(chat_id, doc["current_msg_id"])
        except Exception:
            pass
        tracks.append(track)
        msg_id = await _send_track(context, chat_id, track, user)
        _save(chat_id, tracks, current=track, current_msg_id=msg_id)
        await status.edit_text(f"✅ Ab baj raha hai: <b>{track['title']}</b>", parse_mode="HTML")
        return

    tracks.append(track)
    msg_id = await _send_track(context, chat_id, track, user)
    _save(chat_id, tracks, current=track, current_msg_id=msg_id)
    try:
        await status.delete()
    except Exception:
        pass


# ---------------- /pause /resume (honest) ----------------

async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⏸️ <b>Sach baat:</b> chat audio Telegram app me play hota hai — pause/resume "
        "bot side se possible nahi (app pe hi chalta hai).\n\n"
        "🎮 Jo REAL kaam karta hai: ⏭️ /next ⏮️ /previous ⏹️ stop 🔀 shuffle\n"
        "🎧 Voice chat me bajwana hai to bolna — wo VC player (Option B) bana denge!",
        parse_mode="HTML",
    )


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await cmd_pause(update, context)


# ---------------- /next /previous /np /queue ----------------

async def _skip(context, chat_id, direction, editor=None, user="Queue"):
    doc = _get(chat_id)
    tracks = doc.get("tracks", [])
    current = doc.get("current")
    if not tracks:
        msg = "🎶 Queue khali — /play se gaana lagao!"
        if editor:
            await editor.answer(msg, show_alert=True)
        else:
            await context.bot.send_message(chat_id, msg)
        return

    idx = tracks.index(current) if current in tracks else 0
    idx = (idx + 1) % len(tracks) if direction == "next" else (idx - 1) % len(tracks)
    track = tracks[idx]

    # purana audio delete + uska temp file clean
    if current and current != track and current.get("path"):
        await _cleanup(current["path"])
    if doc.get("current_msg_id"):
        try:
            await context.bot.delete_message(chat_id, doc["current_msg_id"])
        except Exception:
            pass

    msg_id = await _send_track(context, chat_id, track, user)
    _save(chat_id, tracks, current=track, current_msg_id=msg_id)
    if editor:
        await editor.answer("⏭️ Agla gaana!" if direction == "next" else "⏮️ Pichla gaana!")


async def cmd_next(update, context):
    await _skip(context, update.effective_chat.id, "next", user=update.effective_user.first_name)


async def cmd_previous(update, context):
    await _skip(context, update.effective_chat.id, "prev", user=update.effective_user.first_name)


async def cmd_np(update, context):
    doc = _get(update.effective_chat.id)
    t = doc.get("current")
    if not t:
        await update.message.reply_text("🤷 Kuch chal nahi raha. /play likho!")
        return
    await update.message.reply_text(
        f"🎧 <b>NOW PLAYING</b>\n\n🎵 <b>{t['title']}</b>\n"
        f"👤 <i>{t['uploader']}</i>  •  ⏱️ {_fmt(t['duration'])}",
        parse_mode="HTML",
    )


async def cmd_queue(update, context):
    tracks = _get(update.effective_chat.id).get("tracks", [])
    if not tracks:
        await update.message.reply_text("🎶 Queue khali! /play se add karo.")
        return
    lines = [f"🎶 <b>QUEUE</b> ({len(tracks)} songs)\n"]
    for i, t in enumerate(tracks, 1):
        lines.append(f"{i}. <b>{t['title']}</b> — <i>{_fmt(t.get('duration'))}</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ---------------- buttons ----------------

async def on_music_button(update, context):
    query = update.callback_query
    parts = (query.data or "").split(":")
    if len(parts) < 3:
        return
    action, chat_id = parts[1], int(parts[2])

    try:
        member = await context.bot.get_chat_member(chat_id, query.from_user.id)
        if member.status not in ("administrator", "creator"):
            await query.answer("Sirf admins hi control kar sakte hain 😅", show_alert=True)
            return
    except Exception:
        pass

    if action == "stop":
        doc = _get(chat_id)
        t = doc.get("current")
        if t and t.get("path"):
            await _cleanup(t["path"])
        if doc.get("current_msg_id"):
            try:
                await context.bot.delete_message(chat_id, doc["current_msg_id"])
            except Exception:
                pass
        _queue_col.delete_one({"chat_id": chat_id})
        await query.answer("⏹️ Player band!")
        await context.bot.send_message(chat_id, "⏹️ <b>Player band ho gaya.</b> Naya: /play", parse_mode="HTML")
    elif action == "next":
        await _skip(context, chat_id, "next", editor=query, user=query.from_user.first_name)
    elif action == "prev":
        await _skip(context, chat_id, "prev", editor=query, user=query.from_user.first_name)
    elif action == "shuffle":
        doc = _get(chat_id)
        tracks = doc.get("tracks", [])
        if len(tracks) < 2:
            await query.answer("2+ songs chahiye shuffle ke liye!", show_alert=True)
            return
        random.shuffle(tracks)
        _save(chat_id, tracks, current=tracks[0], current_msg_id=doc.get("current_msg_id"))
        await _skip(context, chat_id, "next", editor=query, user=query.from_user.first_name)
    else:
        await query.answer()
