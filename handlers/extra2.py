"""handlers/extra2.py — Advanced Utility Pack (bina API key, free tier friendly)

Features: /weather /wiki /qr /calc /time /shorturl /guess
Sab free APIs use karte hain — wttr.in, Wikipedia, is.gd, qrserver.
"""

import ast
import logging
import math
import operator
import random
import database as db
from datetime import datetime, timedelta, timezone

import httpx
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

TIMEOUT = 15.0
HEADERS = {"User-Agent": "ManagerBot/1.0 (Telegram group bot)"}


async def _typing(context, chat_id):
    try:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
    except Exception:
        pass


# ---------------- /weather (wttr.in — free, no key) ----------------

async def cmd_weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🌤️ <b>Usage:</b> /weather &lt;city&gt;\n"
            "📌 Example: /weather Mumbai ya /weather Delhi",
            parse_mode="HTML",
        )
        return
    city = " ".join(context.args)
    await _typing(context, update.effective_chat.id)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            r = await client.get(
                f"https://wttr.in/{city}", params={"format": "j1"}, headers=HEADERS
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("Weather API fail: %s", e)
        await update.message.reply_text("😅 Mausam wale mood me nahi hain, API chup hai. Thodi der baad try karo!")
        return

    try:
        cur = data["current_condition"][0]
        today = data["weather"][0]
        desc = cur["weatherDesc"][0]["value"]
        emoji = "☀️" if "sun" in desc.lower() or "clear" in desc.lower() else \
                "⛅" if "cloud" in desc.lower() else \
                "🌧️" if "rain" in desc.lower() or "drizzle" in desc.lower() else \
                "⛈️" if "thunder" in desc.lower() else \
                "🌫️" if "mist" in desc.lower() or "fog" in desc.lower() else "🌡️"
        text = (
            f"{emoji} <b>Mausam: {city.title()}</b>\n\n"
            f"🌡️ Temp: <b>{cur['temp_C']}°C</b> (feel: {cur['FeelsLikeC']}°C)\n"
            f"☁️ {desc}\n"
            f"💧 Humidity: {cur['humidity']}%\n"
            f"💨 Hawa: {cur['windspeedKmph']} km/h ({cur['winddir16Point']})\n"
            f"🌫️ Visibility: {cur.get('visibility', '?')} km\n\n"
            f"📅 <b>Aaj:</b> {today['mintempC']}°C — {today['maxtempC']}°C\n"
            f"📅 <b>Kal:</b> {data['weather'][1]['mintempC']}°C — {data['weather'][1]['maxtempC']}°C\n\n"
            f"<i>Chhatri le lo ya nahi, tumhari marzi. 😏</i>"
        )
    except (KeyError, IndexError):
        await update.message.reply_text("🤔 Ye city mil nahi rahi. Spelling check karo — '/weather Mumbai' jaise likho.")
        return
    await update.message.reply_text(text, parse_mode="HTML")


# ---------------- /wiki (Wikipedia REST API — free, no key) ----------------

async def cmd_wiki(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "📚 <b>Usage:</b> /wiki &lt;topic&gt;\n📌 Example: /wiki Black Hole",
            parse_mode="HTML",
        )
        return
    query = " ".join(context.args)
    await _typing(context, update.effective_chat.id)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS) as client:
            s = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": query,
                        "format": "json", "srlimit": 1},
            )
            s.raise_for_status()
            results = s.json().get("query", {}).get("search", [])
            if not results:
                await update.message.reply_text("😕 Wikipedia pe kuch nahi mila. Kuch aur try karo!")
                return
            title = results[0]["title"]
            r = await client.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("Wiki API fail: %s", e)
        await update.message.reply_text("😅 Wikipedia thoda busy hai, dobara try karo.")
        return

    extract = data.get("extract") or "Koi summary nahi mili."
    if len(extract) > 1200:
        extract = extract[:1200] + "…"
    link = data.get("content_urls", {}).get("desktop", {}).get("page", "")
    desc = data.get("description", "")
    text = f"📚 <b>{data.get('title', query)}</b>"
    if desc:
        text += f"\n<i>{desc}</i>"
    text += f"\n\n{extract}"
    if link:
        text += f"\n\n🔗 {link}"
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=False)


# ---------------- /qr (qrserver API — free, no key) ----------------

async def cmd_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "📱 <b>Usage:</b> /qr &lt;text ya link&gt;\n📌 Example: /qr https://t.me/theteamvb",
            parse_mode="HTML",
        )
        return
    data = " ".join(context.args)
    if len(data) > 800:
        await update.message.reply_text("😱 Itna lamba QR nahi ban sakta! Chhota text do (max 800 chars).")
        return
    url = f"https://api.qrserver.com/v1/create-qr-code/?size=500x500&data={data}"
    await update.message.reply_photo(url, caption=f"📱 QR ready! Scan karke dekho — <i>{data[:60]}</i>", parse_mode="HTML")


# ---------------- /calc (safe math — koi API nahi, instant) ----------------

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}
_FUNCS = {n: getattr(math, n) for n in (
    "sqrt", "sin", "cos", "tan", "log", "log2", "log10",
    "factorial", "fabs", "degrees", "radians", "exp",
)}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _safe_eval(node.operand)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.Name) and node.id in ("pi", "e", "tau"):
        return getattr(math, node.id)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        return _FUNCS[node.func.id](*[_safe_eval(a) for a in node.args])
    raise ValueError("invalid")


async def cmd_calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🧮 <b>Usage:</b> /calc &lt;expression&gt;\n"
            "📌 Example: /calc 5*(3+2)^2\n"
            "✨ Functions: sqrt, sin, cos, tan, log, log2, log10, factorial, fabs\n"
            "✨ Constants: pi, e, tau",
            parse_mode="HTML",
        )
        return
    expr = " ".join(context.args).replace("^", "**")
    try:
        result = _safe_eval(ast.parse(expr, mode="eval"))
        if isinstance(result, float) and result == int(result):
            result = int(result)
        await update.message.reply_text(f"🧮 <code>{expr.replace('**', '^')}</code>\n\n✅ <b>{result}</b>", parse_mode="HTML")
    except ZeroDivisionError:
        await update.message.reply_text("➗ Zero se divide? Maths ne tumse naraz ho gaya hai. 😂")
    except Exception:
        await update.message.reply_text("🤕 Ye expression samajh nahi aaya. Sirf maths wale cheezein likho — /calc bina argument ke examples dekho.")


# ---------------- /time (offline — hamesha chalega) ----------------

_ZONES = {
    "IST": 5.5, "UTC": 0, "GMT": 0, "PKT": 5.0, "GST": 4.0,
    "EST": -5.0, "CET": 1.0, "JST": 9.0, "AEST": 10.0, "PST": -8.0,
}


async def cmd_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["🕐 <b>Abhi ka time:</b>\n"]
    now_utc = datetime.now(timezone.utc)
    for name, offset in _ZONES.items():
        t = now_utc + timedelta(hours=offset)
        lines.append(f"{'🇮🇳' if name == 'IST' else '🌍'} <b>{name}:</b> {t.strftime('%I:%M %p')} ({t.strftime('%a, %d %b')})")
    lines.append("\n<i>Sone ka time toh hamesha hota hai — bas maan ki baat. 😴</i>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ---------------- /shorturl (is.gd — free, no key) ----------------

async def cmd_shorturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "🔗 <b>Usage:</b> /shorturl &lt;link&gt;\n📌 Example: /shorturl https://youtube.com/watch?v=xyz...",
            parse_mode="HTML",
        )
        return
    long_url = context.args[0]
    if not long_url.startswith(("http://", "https://")):
        long_url = "https://" + long_url
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get("https://is.gd/create.php", params={"format": "json", "url": long_url})
            r.raise_for_status()
            short = r.json().get("shorturl")
    except Exception as e:
        logger.warning("is.gd fail: %s", e)
        await update.message.reply_text("😅 Link chhota nahi ho paya, thodi der baad try karo.")
        return
    if not short:
        await update.message.reply_text("🤔 Ye link valid nahi lag raha. Pura link dobara check karo.")
        return
    await update.message.reply_text(f"🔗 <b>Short link ready:</b>\n\n{short}", parse_mode="HTML")


# ---------------- /guess — group guessing game 🎮 (MongoDB-backed) ----------------

async def cmd_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user.first_name

    # Bina number ke = game start / status
    if not context.args:
        game = db.get_guess_game(chat_id)
        if game:
            await update.message.reply_text(
                f"🎮 Game pehle se chal raha hai! Ab tak {game['tries']} guess ho chuke.\n"
                "📌 Guess karo: /guess 50"
            )
            return
        number = random.randint(1, 100)
        db.set_guess_game(chat_id, number)
        await update.message.reply_text(
            "🎮 <b>NUMBER GUESSING GAME!</b>\n\n"
            "🤖 Maine 1 se 100 ke beech ek number socha hai...\n"
            "🎯 Tumhe kam se kam guess me dhundhna hai!\n"
            "📌 Guess karo: <code>/guess 50</code>\n\n"
            "<i>Kaun banega is group ka Sherlock Holmes? 🔍</i>",
            parse_mode="HTML",
        )
        return

    # Number ke saath = guess
    game = db.get_guess_game(chat_id)
    if not game:
        await update.message.reply_text(
            "🎮 Pehle game start karo — bas <code>/guess</code> likho, bina number ke!",
            parse_mode="HTML",
        )
        return

    arg = context.args[0].lstrip("-")
    if not arg.isdigit():
        await update.message.reply_text("🔢 Number batao bhai — /guess 50 jaise!")
        return

    guess = int(context.args[0])
    secret = game["number"]
    db.add_guess_try(chat_id)

    # Hints ab bilkul unambiguous: "MERA NUMBER tumhare guess se bada/chhota hai"
    if secret > guess:
        await update.message.reply_text(
            f"📈 {user}: <b>{guess}</b> — Galat! Mera number isse <b>BADA</b> hai ⬆️",
            parse_mode="HTML",
        )
    elif secret < guess:
        await update.message.reply_text(
            f"📉 {user}: <b>{guess}</b> — Galat! Mera number isse <b>CHHOTA</b> hai ⬇️",
            parse_mode="HTML",
        )
    else:
        tries = game["tries"] + 1
        db.delete_guess_game(chat_id)
        if tries <= 5:
            praise = "🥳 Legend ho tum!"
        elif tries <= 10:
            praise = "👍 Sahi toh hai, bas thoda lamba khel gaye."
        else:
            praise = "🐌 Pahunch toh gaye, bas raste me thoda ghoom aaye."
        await update.message.reply_text(
            f"🎉🎉🎉 <b>SHABASH {user}!</b>\n\n"
            f"🎯 Number <b>{guess}</b> hi tha!\n"
            f"🏆 Sirf <b>{tries} guesses</b> me pakad liya!\n\n"
            f"{praise}\n\nNaya game? <code>/guess</code> likho!",
            parse_mode="HTML",
        )
