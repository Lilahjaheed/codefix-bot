import os
import time
import logging
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_KEY_HERE")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-flash-lite-latest:generateContent"
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LANGUAGES = {
    "python": "🐍 Python",
    "javascript": "🟨 JavaScript",
    "java": "☕ Java",
    "react": "⚛️ React",
    "htmlcss": "🌐 HTML/CSS",
    "cpp": "➕ C++",
    "go": "🐹 Go",
}

SYSTEM_PROMPTS = {
    "python": "You are a Python coding expert. Give working Python code first, then a short explanation. Use proper code blocks with ```python tags.",
    "javascript": "You are a JavaScript coding expert. Give working JS code first, then a short explanation. Use proper code blocks with ```javascript tags.",
    "java": "You are a Java coding expert. Give working Java code first, then a short explanation. Use proper code blocks with ```java tags.",
    "react": "You are a React coding expert. Give working React/JSX code first, then a short explanation. Use proper code blocks with ```jsx tags.",
    "htmlcss": "You are an HTML/CSS expert. Give working HTML/CSS code first, then a short explanation. Use proper code blocks with ```html tags.",
    "cpp": "You are a C++ coding expert. Give working C++ code first, then a short explanation. Use proper code blocks with ```cpp tags.",
    "go": "You are a Go coding expert. Give working Go code first, then a short explanation. Use proper code blocks with ```go tags.",
    "any": "You are a coding assistant. Infer the language from the user's question. Give working code first, then a short explanation. Use proper code blocks with language tags.",
}


def ask_gemini(prompt: str, retries: int = 3) -> str:
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 2048},
                },
                timeout=(10, 60),
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.warning(f"Gemini attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(2 * attempt)
    raise RuntimeError("Gemini API failed after all retries")


def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Change Language", callback_data="menu_lang")],
        [InlineKeyboardButton("💡 Example Prompt", callback_data="menu_example")],
        [InlineKeyboardButton("ℹ️ About", callback_data="menu_about")],
        [InlineKeyboardButton("🔄 Reset Session", callback_data="menu_reset")],
    ])


def language_keyboard():
    buttons = []
    row = []
    for key, label in LANGUAGES.items():
        row.append(InlineKeyboardButton(label, callback_data=f"setlang_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🤖 Auto-detect", callback_data="setlang_any")])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="menu_home")])
    return InlineKeyboardMarkup(buttons)


def back_to_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu_home")]
    ])


async def send_menu(update_or_query, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
    lang_key = context.user_data.get("language", "any")
    lang_label = LANGUAGES.get(lang_key, "🤖 Auto-detect")

    text = (
        "🤖 *CodeFix Bot*\n\n"
        f"🌍 Current language: *{lang_label}*\n\n"
        "Send me any coding question — a bug, a feature, or \"write me a...\" — "
        "and I'll reply with working code.\n\n"
        "Use the buttons below to navigate:"
    )

    keyboard = main_menu_keyboard()

    if edit:
        msg = update_or_query.message
        try:
            await msg.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        except Exception:
            await msg.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await update_or_query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["language"] = context.user_data.get("language", "any")
    await send_menu(update, context)


async def menu_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_home":
        await send_menu(update, context, edit=True)

    elif data == "menu_lang":
        lang_key = context.user_data.get("language", "any")
        lang_label = LANGUAGES.get(lang_key, "🤖 Auto-detect")
        text = (
            f"🌍 *Language Settings*\n\n"
            f"Current: *{lang_label}*\n\n"
            "Pick a language below — your choice is remembered "
            "until you change it."
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=language_keyboard())

    elif data == "menu_example":
        lang_key = context.user_data.get("language", "any")
        examples = {
            "python": "Fix this bug:\ndef add(a, b):\n    return a - b\n\n# Also add type hints and a docstring",
            "javascript": "Write a debounce function in JS with a clear example",
            "java": "Write a Java method that checks if a string is a palindrome",
            "react": "Build a React counter component with useState",
            "htmlcss": "Build a responsive navbar with a hamburger menu",
            "cpp": "Write a C++ program to reverse a linked list",
            "go": "Write a Go HTTP server with a /hello endpoint",
            "any": "Write a Python function that finds the longest word in a sentence",
        }
        example = examples.get(lang_key, examples["any"])
        text = (
            "💡 *Example Prompt*\n\n"
            "Copy, edit, and send this:\n\n"
            f"`{example}`\n\n"
            "I'll reply with working code + explanation."
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_to_menu_keyboard())

    elif data == "menu_about":
        text = (
            "ℹ️ *About CodeFix Bot*\n\n"
            "I solve coding problems in 7+ languages using Google Gemini AI.\n\n"
            "*What I can do:*\n"
            "• Fix bugs in your code\n"
            "• Write functions from scratch\n"
            "• Explain tricky code\n"
            "• Convert between languages\n\n"
            "*How to use:*\n"
            "1. Pick your language (or use auto-detect)\n"
            "2. Send your code or question\n"
            "3. Get a working answer instantly\n\n"
            "Built with 💛 by [your name]"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_to_menu_keyboard())

    elif data == "menu_reset":
        context.user_data["language"] = "any"
        context.user_data.pop("history", None)
        await query.edit_message_text(
            "✅ Session reset.\n\nLanguage: 🤖 Auto-detect\n\nSend me your first coding question!",
            reply_markup=main_menu_keyboard(),
        )


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang_key = query.data.replace("setlang_", "")
    context.user_data["language"] = lang_key

    if lang_key == "any":
        label = "🤖 Auto-detect"
    else:
        label = LANGUAGES.get(lang_key, lang_key)

    await query.edit_message_text(
        f"✅ Language set to *{label}*\n\nNow send your coding question!",
        parse_mode="Markdown",
        reply_markup=back_to_menu_keyboard(),
    )


async def solve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    lang_key = context.user_data.get("language", "any")

    if lang_key == "any":
        prompt = (
            "You are a coding assistant. Infer the language from the user's question. "
            "Give working code first, then a short explanation. "
            "Use proper code blocks with language tags.\n\n"
            f"Problem: {user_msg}"
        )
    else:
        prompt = (
            f"{SYSTEM_PROMPTS.get(lang_key, SYSTEM_PROMPTS['any'])}\n\n"
            f"Problem: {user_msg}"
        )

    status = await update.message.reply_text("⏳ Solving...")

    try:
        answer = ask_gemini(prompt)

        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n... (truncated)"

        try:
            await status.edit_text(answer)
        except Exception:
            await update.message.reply_text(answer)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❓ Another question", callback_data="menu_home"),
             InlineKeyboardButton("🌍 Change language", callback_data="menu_lang")],
        ])
        await update.message.reply_text("What's next?", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error: {e}")
        try:
            await status.edit_text("❌ Something went wrong. Please try again.")
        except Exception:
            await update.message.reply_text("❌ Something went wrong. Please try again.")


async def post_init(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Open main menu"),
        BotCommand("menu", "Open main menu"),
        BotCommand("lang", "Change language"),
    ])


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
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler(["start", "menu"], start))
    app.add_handler(CommandHandler("lang", menu_nav))
    app.add_handler(CallbackQueryHandler(menu_nav, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(set_language, pattern="^setlang_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, solve))

    threading.Thread(target=run_health_server, daemon=True).start()

    print("🤖 CodeFix Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
