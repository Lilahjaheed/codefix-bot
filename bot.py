import os
import time
import logging
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# --- CONFIG ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_KEY_HERE")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-flash-lite-latest:generateContent"
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ask_gemini(prompt: str, retries: int = 3) -> str:
    """Call Gemini REST API with retry — survives VPN drops."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 2048},
                },
                timeout=(10, 60),  # connect=10s, read=60s
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.warning(f"Gemini attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError("Gemini API failed after all retries")

SYSTEM_PROMPT = """You are a coding assistant bot. Solve coding problems clearly.
Rules:
- Give working code first, then a short explanation
- Support Python, JavaScript, Java, React, HTML, CSS
- If language is not specified, infer from context or default to Python
- Keep answers concise and accurate
- Use proper code blocks with language tags
"""

LANGUAGES = [
    [InlineKeyboardButton("🐍 Python", callback_data="lang_python"),
     InlineKeyboardButton("🟨 JavaScript", callback_data="lang_js")],
    [InlineKeyboardButton("☕ Java", callback_data="lang_java"),
     InlineKeyboardButton("⚛️ React", callback_data="lang_react")],
    [InlineKeyboardButton("🌐 HTML/CSS", callback_data="lang_web"),
     InlineKeyboardButton("💬 Ask anything", callback_data="lang_free")],
]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "👋 Hi! I'm CodeFix Bot\n\n"
        "I solve coding problems in 5+ languages.\n\n"
        "Pick a language or just type your question:\n\n"
        "Example: Fix this Python bug: [paste code]"
    )
    keyboard = InlineKeyboardMarkup(LANGUAGES)
    await update.message.reply_text(welcome, reply_markup=keyboard)


async def language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lang_map = {
        "lang_python": "Python",
        "lang_js": "JavaScript",
        "lang_java": "Java",
        "lang_react": "React",
        "lang_web": "HTML/CSS",
        "lang_free": None,
    }

    lang = lang_map.get(query.data)
    if lang:
        context.user_data["language"] = lang
        await query.edit_message_text(
            f"✅ Language set to {lang}\n\nNow send your code or question:"
        )
    else:
        context.user_data["language"] = None
        await query.edit_message_text(
            "✅ Free mode. Send your coding question:"
        )


async def solve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    lang = context.user_data.get("language", "Python")

    await update.message.reply_text("⏳ Solving...")

    try:
        prompt = f"{SYSTEM_PROMPT}\nLanguage preference: {lang}\n\nProblem: {user_msg}"
        answer = ask_gemini(prompt)

        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n... (truncated)"

        await update.message.reply_text(answer)
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(
            "❌ Error solving. Please try again."
        )


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass


def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"Health server on :{port}")
    server.serve_forever()


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(language_choice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, solve))

    threading.Thread(target=run_health_server, daemon=True).start()

    print("🤖 CodeFix Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
