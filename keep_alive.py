import threading
import time
from flask import Flask, jsonify
from config import PORT, BOT_NAME, BOT_CREDIT

app = Flask(__name__)
_start_time = time.time()


@app.route("/")
def home():
    return f"{BOT_NAME} is alive! {BOT_CREDIT}"


@app.route("/ping")
def ping():
    return "pong"


@app.route("/health")
def health():
    uptime_seconds = int(time.time() - _start_time)
    return jsonify(
        {
            "status": "ok",
            "bot": BOT_NAME,
            "credit": BOT_CREDIT,
            "uptime_seconds": uptime_seconds,
        }
    )


def run():
    app.run(host="0.0.0.0", port=PORT)


def keep_alive():
    """Starts the Flask server in a background thread so it doesn't block the bot."""
    t = threading.Thread(target=run, daemon=True)
    t.start()
