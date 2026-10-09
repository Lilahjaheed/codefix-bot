import os
import re
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

DEV_USERNAME = "Mathsadiq"
DEV_URL = "https://t.me/Mathsadiq"
PORTFOLIO_URL = "https://mathsadiq.netlify.app"

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
    "python": (
        "You are a Python coding expert.\n\n"
        "RULES:\n"
        "- If the user asks for code/fix/build → give working code in a ```python block, then a short explanation.\n"
        "- If the user asks a conceptual question (how to learn, what is, difference between) → "
        "give a clear structured answer. Only include code if it truly helps. Keep it beginner-friendly.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers concise. No fluff."
    ),
    "javascript": (
        "You are a JavaScript coding expert.\n\n"
        "RULES:\n"
        "- If the user asks for code/fix/build → give working code in a ```javascript block, then a short explanation.\n"
        "- If the user asks a conceptual question → give a clear structured answer. Only include code if it truly helps.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers concise. No fluff."
    ),
    "java": (
        "You are a Java coding expert.\n\n"
        "RULES:\n"
        "- If the user asks for code/fix/build → give working code in a ```java block, then a short explanation.\n"
        "- If the user asks a conceptual question → give a clear structured answer. Only include code if it truly helps.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers concise. No fluff."
    ),
    "react": (
        "You are a React coding expert.\n\n"
        "RULES:\n"
        "- If the user asks for code/fix/build → give working code in a ```jsx block, then a short explanation.\n"
        "- If the user asks a conceptual question → give a clear structured answer. Only include code if it truly helps.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers concise. No fluff."
    ),
    "htmlcss": (
        "You are an HTML/CSS expert.\n\n"
        "RULES:\n"
        "- If the user asks for code/fix/build → give working code in a ```html block, then a short explanation.\n"
        "- If the user asks a conceptual question → give a clear structured answer. Only include code if it truly helps.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers concise. No fluff."
    ),
    "cpp": (
        "You are a C++ coding expert.\n\n"
        "RULES:\n"
        "- If the user asks for code/fix/build → give working code in a ```cpp block, then a short explanation.\n"
        "- If the user asks a conceptual question → give a clear structured answer. Only include code if it truly helps.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers concise. No fluff."
    ),
    "go": (
        "You are a Go coding expert.\n\n"
        "RULES:\n"
        "- If the user asks for code/fix/build → give working code in a ```go block, then a short explanation.\n"
        "- If the user asks a conceptual question → give a clear structured answer. Only include code if it truly helps.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers concise. No fluff."
    ),
    "any": (
        "You are a coding assistant.\n\n"
        "RULES:\n"
        "- Infer the language from context.\n"
        "- If the user asks for code/fix/build → give working code in a ``` block with the correct language tag, then a short explanation.\n"
        "- If the user asks a conceptual question (how to learn, what is, difference between) → "
        "give a clear structured answer. Only include code if it truly helps. Keep it beginner-friendly.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers concise. No fluff."
    ),
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
        [InlineKeyboardButton("ℹ️ About", callback_data="menu_about"),
         InlineKeyboardButton("👨‍💻 Hire Dev", callback_data="menu_hire")],
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
        "🤖 *ProCoderBot*\n\n"
        f"🌍 Current language: *{lang_label}*\n\n"
        "Send me any coding question — a bug, a feature, or \"write me a...\" — "
        "and I'll reply with working code.\n\n"
        f"👨‍💻 Built by [@{DEV_USERNAME}]({DEV_URL})"
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
            "ℹ️ *About ProCoderBot*\n\n"
            "I solve coding problems in 7+ languages.\n\n"
            "*What I can do:*\n"
            "• Fix bugs in your code\n"
            "• Write functions from scratch\n"
            "• Explain tricky code\n"
            "• Convert between languages\n\n"
            "*How to use:*\n"
            "1. Pick your language (or use auto-detect)\n"
            "2. Send your code or question\n"
            "3. Get a working answer instantly\n\n"
            f"Built with 💛 by [@{DEV_USERNAME}]({DEV_URL})\n"
            f"🌐 [Portfolio]({PORTFOLIO_URL})"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_to_menu_keyboard())

    elif data == "menu_hire":
        text = (
            "👨‍💻 *Need a developer?*\n\n"
            f"I'm [@{DEV_USERNAME}]({DEV_URL}) — I build:\n\n"
            "🤖 *Telegram Bots*\n"
            "AI-powered bots, automation, payment integration\n\n"
            "🌐 *Web Development*\n"
            "Landing pages, full-stack apps, 3D scroll sites\n\n"
            "🎬 *Video Editing*\n"
            "Promos, edits, motion graphics\n\n"
            "💬 *Transcription*\n"
            "Audio/video to text, captions, subtitles\n\n"
            "— — — — — — — — —\n"
            "👇 Tap below to contact me"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Message me on Telegram", url=DEV_URL)],
            [InlineKeyboardButton("🌐 View Portfolio", url=PORTFOLIO_URL)],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu_home")],
        ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

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


def format_answer(raw: str) -> str:
    """Separate code blocks from explanation. Convert **bold** to Telegram *bold*."""
    import re

    # Convert **bold** (Gemini style) to *bold* (Telegram style)
    raw = re.sub(r"\*\*(.+?)\*\*", r"*\1*", raw)

    parts = re.split(r"(```(?:\w+)?\n.*?```)", raw, flags=re.DOTALL)

    formatted = []
    for part in parts:
        if part.startswith("```"):
            code = part.strip()
            lang_match = re.match(r"```(\w+)?", code)
            lang = lang_match.group(1) if lang_match and lang_match.group(1) else ""
            formatted.append(
                f"━━━━━━━━━━ 📦 CODE {('· ' + lang.upper()) if lang else ''} ━━━━━━━━━━\n\n"
                f"{code}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        elif part.strip():
            formatted.append(
                f"📖 *EXPLANATION*\n\n{part.strip()}"
            )

    return "\n\n".join(formatted)


GREETINGS = {
    "hi", "hello", "hey", "yo", "sup", "hola", "salam", "hiya",
    "good morning", "good afternoon", "good evening", "good night",
    "how are you", "how are u", "whats up", "what's up", "wassup",
    "hii", "helloo", "heyy", "hi there", "hey there", "test",
    "ok", "okay", "cool", "nice", "great", "thanks", "thank you",
    "bye", "goodbye", "see you", "cya",
}

GREETING_REPLIES = {
    "greet": (
        "👋 Hey! I'm ProCoderBot.\n\n"
        "I solve coding problems — just send me your question!\n\n"
        "Examples:\n"
        "• Fix this bug: [paste code]\n"
        "• Write a Python function to sort a list\n"
        "• How do I center a div in CSS?\n\n"
        "Pick a language below or just ask anything:"
    ),
    "howru": (
        "😊 I'm doing great, thanks for asking!\n\n"
        "Ready to help with your code — what do you need?"
    ),
    "thanks": (
        "🙏 You're welcome!\n\n"
        "Got more code problems? Send them anytime."
    ),
    "bye": (
        "👋 Bye! Come back anytime you need code help.\n\n"
        "Need a developer? [@Mathsadiq](https://t.me/Mathsadiq) — bots, websites, video editing."
    ),
}


def detect_greeting(text: str) -> str | None:
    t = text.lower().strip()
    if t in ("hi", "hello", "hey", "yo", "sup", "hola", "salam", "hiya",
             "hii", "helloo", "heyy", "hi there", "hey there", "test",
             "good morning", "good afternoon", "good evening"):
        return "greet"
    if t in ("how are you", "how are u", "whats up", "what's up", "wassup",
             "how's it going", "how is it going"):
        return "howru"
    if t in ("thanks", "thank you", "thx", "ty", "appreciate it"):
        return "thanks"
    if t in ("bye", "goodbye", "see you", "cya", "good night"):
        return "bye"
    return None


async def solve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    lang_key = context.user_data.get("language", "any")

    greeting_type = detect_greeting(user_msg)
    if greeting_type:
        reply = GREETING_REPLIES[greeting_type]
        keyboard = main_menu_keyboard()
        await update.message.reply_text(
            reply, parse_mode="Markdown", reply_markup=keyboard
        )
        return

    if lang_key == "any":
        prompt = (
            "You are a coding assistant.\n\n"
            "RULES:\n"
            "- Infer the language from context.\n"
            "- If the user asks for code/fix/build → give working code in a ``` block with the correct language tag, then a short explanation.\n"
            "- If the user asks a conceptual question (how to learn, what is, difference between) → "
            "give a clear structured answer. Only include code if it truly helps. Keep it beginner-friendly.\n"
            "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
            "- Keep answers concise. No fluff.\n\n"
            f"Problem: {user_msg}"
        )
    else:
        prompt = (
            f"{SYSTEM_PROMPTS.get(lang_key, SYSTEM_PROMPTS['any'])}\n\n"
            f"Problem: {user_msg}"
        )

    status = await update.message.reply_text("⏳ Solving...")

    # Track message count — show ad on 1st, 4th, 7th... (every 3rd)
    count = context.user_data.get("msg_count", 0) + 1
    context.user_data["msg_count"] = count
    show_ad = (count == 1) or (count % 3 == 1)

    try:
        answer = ask_gemini(prompt)
        answer = format_answer(answer)

        if len(answer) > 4000:
            answer = answer[:4000] + "\n\n... (truncated)"

        try:
            await status.edit_text(answer, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(answer)

        if show_ad:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("❓ Another question", callback_data="menu_home"),
                 InlineKeyboardButton("🌍 Language", callback_data="menu_lang")],
                [InlineKeyboardButton("👨‍💻 Hire the developer", url=DEV_URL),
                 InlineKeyboardButton("🌐 Portfolio", url=PORTFOLIO_URL)],
            ])
            await update.message.reply_text(
                f"🔧 Built by [@{DEV_USERNAME}]({DEV_URL}) · Need a bot or website? Tap below.",
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("❓ Another question", callback_data="menu_home"),
                 InlineKeyboardButton("🌍 Language", callback_data="menu_lang")],
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

    print("🤖 ProCoderBot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
