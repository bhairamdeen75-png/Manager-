import os

# --- Required ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Comma separated telegram user ids who are bot owners (can use owner-only commands)
OWNER_IDS = [
    int(x) for x in os.getenv("OWNER_IDS", "").replace(" ", "").split(",") if x
]

# --- Keep-alive web server (for Render) ---
PORT = int(os.getenv("PORT", "8080"))

# --- Anti-spam settings ---
FLOOD_MSG_LIMIT = int(os.getenv("FLOOD_MSG_LIMIT", "5"))     # messages
FLOOD_TIME_WINDOW = int(os.getenv("FLOOD_TIME_WINDOW", "7"))  # seconds
FLOOD_MUTE_MINUTES = int(os.getenv("FLOOD_MUTE_MINUTES", "10"))

# --- Warn settings ---
MAX_WARNS = int(os.getenv("MAX_WARNS", "3"))

# --- Captcha settings ---
CAPTCHA_TIMEOUT_SECONDS = int(os.getenv("CAPTCHA_TIMEOUT_SECONDS", "90"))

# --- Database (MongoDB) ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "telegram_manager_bot")

# --- Bot identity ---
BOT_NAME = "Manager"
BOT_CREDIT = "Made with ❤️ TEAMVB"

# --- XP system ---
XP_MIN_PER_MESSAGE = int(os.getenv("XP_MIN_PER_MESSAGE", "1"))
XP_MAX_PER_MESSAGE = int(os.getenv("XP_MAX_PER_MESSAGE", "3"))
XP_COOLDOWN_SECONDS = int(os.getenv("XP_COOLDOWN_SECONDS", "30"))

# --- Free dictionary API (no key required) ---
DICTIONARY_API_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"

# --- Tag-all ---
TAGALL_CHUNK_SIZE = int(os.getenv("TAGALL_CHUNK_SIZE", "5"))  # mentions per message
