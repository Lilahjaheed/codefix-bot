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

# Security: Owner Telegram user ID (only you can use admin commands)
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))  # Set this in Render env vars

# Security: Rate limiting
RATE_LIMIT_MESSAGES = 5  # Max messages per window
RATE_LIMIT_WINDOW = 60   # Seconds

# Security: Blocked users (user_id: reason)
blocked_users = {}

# Security: User message timestamps for rate limiting
user_timestamps = {}

# Security: Stats
stats = {
    "total_users": set(),
    "total_messages": 0,
    "blocked_attempts": 0,
    "rate_limited": 0,
}

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-flash-lite-latest:generateContent"
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_blocked(user_id: int) -> bool:
    return user_id in blocked_users


def check_rate_limit(user_id: int) -> bool:
    """Returns True if user is rate limited."""
    now = time.time()
    if user_id not in user_timestamps:
        user_timestamps[user_id] = []

    # Remove old timestamps outside the window
    user_timestamps[user_id] = [
        ts for ts in user_timestamps[user_id]
        if now - ts < RATE_LIMIT_WINDOW
    ]

    if len(user_timestamps[user_id]) >= RATE_LIMIT_MESSAGES:
        stats["rate_limited"] += 1
        return True

    user_timestamps[user_id].append(now)
    return False

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
        "- Keep answers SHORT and focused. Max 150 words for explanations. No fluff."
    ),
    "javascript": (
        "You are a JavaScript coding expert.\n\n"
        "RULES:\n"
        "- If the user asks for code/fix/build → give working code in a ```javascript block, then a short explanation.\n"
        "- If the user asks a conceptual question → give a clear structured answer. Only include code if it truly helps.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers SHORT and focused. Max 150 words for explanations. No fluff."
    ),
    "java": (
        "You are a Java coding expert.\n\n"
        "RULES:\n"
        "- If the user asks for code/fix/build → give working code in a ```java block, then a short explanation.\n"
        "- If the user asks a conceptual question → give a clear structured answer. Only include code if it truly helps.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers SHORT and focused. Max 150 words for explanations. No fluff."
    ),
    "react": (
        "You are a React coding expert.\n\n"
        "RULES:\n"
        "- If the user asks for code/fix/build → give working code in a ```jsx block, then a short explanation.\n"
        "- If the user asks a conceptual question → give a clear structured answer. Only include code if it truly helps.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers SHORT and focused. Max 150 words for explanations. No fluff."
    ),
    "htmlcss": (
        "You are an HTML/CSS expert.\n\n"
        "RULES:\n"
        "- If the user asks for code/fix/build → give working code in a ```html block, then a short explanation.\n"
        "- If the user asks a conceptual question → give a clear structured answer. Only include code if it truly helps.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers SHORT and focused. Max 150 words for explanations. No fluff."
    ),
    "cpp": (
        "You are a C++ coding expert.\n\n"
        "RULES:\n"
        "- If the user asks for code/fix/build → give working code in a ```cpp block, then a short explanation.\n"
        "- If the user asks a conceptual question → give a clear structured answer. Only include code if it truly helps.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers SHORT and focused. Max 150 words for explanations. No fluff."
    ),
    "go": (
        "You are a Go coding expert.\n\n"
        "RULES:\n"
        "- If the user asks for code/fix/build → give working code in a ```go block, then a short explanation.\n"
        "- If the user asks a conceptual question → give a clear structured answer. Only include code if it truly helps.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers SHORT and focused. Max 150 words for explanations. No fluff."
    ),
    "any": (
        "You are a coding assistant.\n\n"
        "RULES:\n"
        "- Infer the language from context.\n"
        "- If the user asks for code/fix/build → give working code in a ``` block with the correct language tag, then a short explanation.\n"
        "- If the user asks a conceptual question (how to learn, what is, difference between) → "
        "give a clear structured answer. Only include code if it truly helps. Keep it beginner-friendly.\n"
        "- Use Telegram Markdown: *bold* for headers, NOT ### or ##.\n"
        "- Keep answers SHORT and focused. Max 150 words for explanations. No fluff."
    ),
}


def ask_gemini(prompt: str, retries: int = 3) -> str:
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"maxOutputTokens": 1024},
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


def clean_markdown(text: str) -> str:
    """Convert Markdown variants to Telegram Markdown."""
    import re

    # Convert ### Header / ## Header / # Header to *bold*
    text = re.sub(r"^#{1,4}\s*(.+)$", r"*\1*", text, flags=re.MULTILINE)

    # Convert **bold** to *bold*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)

    # Convert ### inline (e.g. ### Explanation) that's mid-line
    text = re.sub(r"###\s*(.+)", r"*\1*", text)

    return text


def split_answer(raw: str) -> tuple[str, str]:
    """Split Gemini response into (explanation, code) parts."""
    import re

    raw = clean_markdown(raw)

    parts = re.split(r"(```(?:\w+)?\n.*?```)", raw, flags=re.DOTALL)

    explanation_parts = []
    code_parts = []

    for part in parts:
        if part.startswith("```"):
            code_parts.append(part.strip())
        elif part.strip():
            explanation_parts.append(part.strip())

    explanation = "\n\n".join(explanation_parts)
    code = "\n\n".join(code_parts)

    return explanation, code


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


IDENTITY_KEYWORDS = [
    "who created you", "who made you", "who built you", "who developed you",
    "who is your developer", "who is your creator", "who is your owner",
    "what created you", "what made you", "what built you",
    "who are you", "what are you", "what is your name", "your name",
    "who is mathsadiq", "who is your maker",
    "where were you deployed", "where are you hosted", "where were you built",
    "what were you built with", "what were you made with", "what tech stack",
    "what model are you", "which ai are you", "are you chatgpt", "are you gemini",
    "are you gpt", "are you an ai", "are you human", "are you a bot",
]


def detect_identity(text: str) -> bool:
    t = text.lower().strip()
    return any(kw in t for kw in IDENTITY_KEYWORDS)


IDENTITY_REPLY = (
    "👋 I'm *ProCoderBot*!\n\n"
    "I was created by [@Mathsadiq](https://t.me/Mathsadiq) — "
    "a developer who builds Telegram bots, websites, and more.\n\n"
    "I'm here to help you with coding problems. "
    "Just send me your question!"
)


NON_CODING_REPLIES = (
    "❌ I'm sorry, I cannot help with that.\n\n"
    "I'm a coding assistant — I only answer questions about:\n"
    "• Programming (Python, JavaScript, Java, C++, Go, React)\n"
    "• HTML/CSS\n"
    "• Debugging code\n"
    "• Learning to code\n\n"
    "Do you have a coding question or problem to solve?"
)

NON_CODING_KEYWORDS = [
    "time", "date", "today", "weather", "temperature",
    "unlock", "phone", "password", "account", "email", "wifi", "internet",
    "book", "novel", "read", "write a story", "poem",
    "door", "open a door", "cook", "recipe", "food", "meal",
    "music", "song", "movie", "film", "game", "play",
    "girlfriend", "boyfriend", "love", "relationship", "marry",
    "money", "rich", "invest", "bitcoin", "crypto", "forex",
    "football", "soccer", "basketball", "nba", "premier league",
    "health", "doctor", "medicine", "sick", "exercise", "gym",
    "school", "homework", "exam", "teacher", "student",
    "president", "government", "politics", "war", "news",
    "joke", "funny", "story", "tell me about",
    "how to sleep", "how to wake", "how to eat", "how to drink",
    "how to walk", "how to run", "how to talk", "how to speak",
    "how to make friends", "how to be happy", "how to be rich",
    "who is", "what is life", "meaning of life", "god", "religion",
]

NON_CODING_EXACT = {
    "what time is it", "what's the time", "what is the time",
    "what date is it", "what's the date", "what is today",
    "how are you", "who are you", "what is your name",
}


def is_non_coding(text: str) -> bool:
    t = text.lower().strip()

    if t in NON_CODING_EXACT:
        return True

    coding_signals = [
        "code", "coding", "program", "function", "bug", "error",
        "python", "javascript", "java", "react", "html", "css",
        "api", "database", "sql", "git", "deploy", "server",
        "def ", "class ", "import ", "return ", "console.log",
        "print(", "var ", "let ", "const ", "int ", "void ",
        "loop", "array", "string", "variable", "algorithm",
        "framework", "library", "npm", "pip", "compile",
        "frontend", "backend", "fullstack", "devops",
        "write a function", "fix this", "debug", "why does",
        "how do i code", "how to code", "how to program",
    ]

    if any(s in t for s in coding_signals):
        return False

    non_coding_score = sum(1 for kw in NON_CODING_KEYWORDS if kw in t)
    if non_coding_score >= 2:
        return True

    question_starters = ("how can i", "how do i", "what is", "who is", "tell me")
    if any(t.startswith(s) for s in question_starters):
        if not any(s in t for s in coding_signals):
            return True

    return False


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner only: Show bot statistics."""
    if not is_owner(update.message.from_user.id):
        return

    total_users = len(stats["total_users"])
    msg = (
        "📊 *Bot Statistics*\n\n"
        f"👥 Total users: {total_users}\n"
        f"💬 Total messages: {stats['total_messages']}\n"
        f"🚫 Rate limited: {stats['rate_limited']}\n"
        f"⛔ Blocked attempts: {stats['blocked_attempts']}\n"
        f"🔒 Blocked users: {len(blocked_users)}\n"
        f"⏰ Uptime: Check Render dashboard"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner only: Broadcast message to all users."""
    if not is_owner(update.message.from_user.id):
        return

    text = update.message.text.replace("/broadcast ", "", 1)
    if not text:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return

    success = 0
    failed = 0
    for user_id in stats["total_users"]:
        try:
            await context.bot.send_message(user_id, text)
            success += 1
        except Exception:
            failed += 1

    await update.message.reply_text(
        f"📢 Broadcast sent!\n✅ Success: {success}\n❌ Failed: {failed}"
    )


async def handle_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner only: Ban a user from using the bot."""
    if not is_owner(update.message.from_user.id):
        return

    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /ban <user_id> [reason]")
        return

    try:
        target_id = int(parts[1])
        reason = " ".join(parts[2:]) if len(parts) > 2 else "No reason"
        blocked_users[target_id] = reason
        await update.message.reply_text(f"⛔ User {target_id} banned.\nReason: {reason}")
    except ValueError:
        await update.message.reply_text("Invalid user ID. Usage: /ban <user_id> [reason]")


async def handle_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner only: Unban a user."""
    if not is_owner(update.message.from_user.id):
        return

    parts = update.message.text.split()
    if len(parts) < 2:
        await update.message.reply_text("Usage: /unban <user_id>")
        return

    try:
        target_id = int(parts[1])
        if target_id in blocked_users:
            del blocked_users[target_id]
            await update.message.reply_text(f"✅ User {target_id} unbanned.")
        else:
            await update.message.reply_text(f"User {target_id} is not banned.")
    except ValueError:
        await update.message.reply_text("Invalid user ID.")


async def handle_blocked_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner only: List all blocked users."""
    if not is_owner(update.message.from_user.id):
        return

    if not blocked_users:
        await update.message.reply_text("No blocked users.")
        return

    msg = "🔒 *Blocked Users*\n\n"
    for uid, reason in blocked_users.items():
        msg += f"• `{uid}` — {reason}\n"

    await update.message.reply_text(msg, parse_mode="Markdown")

    non_coding_score = sum(1 for kw in NON_CODING_KEYWORDS if kw in t)
    if non_coding_score >= 2:
        return True

    question_starters = ("how can i", "how do i", "what is", "who is", "tell me")
    if any(t.startswith(s) for s in question_starters):
        if not any(s in t for s in coding_signals):
            return True

    return False


async def solve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_msg = update.message.text

    # Security: Check if user is blocked
    if is_blocked(user_id):
        stats["blocked_attempts"] += 1
        return  # Silent ignore

    # Security: Rate limiting
    if check_rate_limit(user_id):
        await update.message.reply_text(
            "⏳ Slow down! You're sending too many messages. "
            f"Try again in {RATE_LIMIT_WINDOW} seconds."
        )
        return

    # Track user
    stats["total_users"].add(user_id)
    stats["total_messages"] += 1

    lang_key = context.user_data.get("language", "any")

    # Owner commands
    if is_owner(user_id):
        if user_msg.startswith("/stats"):
            await handle_stats(update, context)
            return
        if user_msg.startswith("/broadcast "):
            await handle_broadcast(update, context)
            return
        if user_msg.startswith("/ban "):
            await handle_ban(update, context)
            return
        if user_msg.startswith("/unban "):
            await handle_unban(update, context)
            return
        if user_msg.startswith("/blocked"):
            await handle_blocked_list(update, context)
            return

    greeting_type = detect_greeting(user_msg)
    if greeting_type:
        reply = GREETING_REPLIES[greeting_type]
        keyboard = main_menu_keyboard()
        await update.message.reply_text(
            reply, parse_mode="Markdown", reply_markup=keyboard
        )
        return

    if detect_identity(user_msg):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👨‍💻 Hire the developer", url=DEV_URL)],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu_home")],
        ])
        await update.message.reply_text(
            IDENTITY_REPLY, parse_mode="Markdown", reply_markup=keyboard
        )
        return

    if is_non_coding(user_msg):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💡 Example Prompt", callback_data="menu_example")],
            [InlineKeyboardButton("⬅️ Back to Menu", callback_data="menu_home")],
        ])
        await update.message.reply_text(
            NON_CODING_REPLIES, reply_markup=keyboard
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
        explanation, code = split_answer(answer)

        # Build single message: code first, explanation below
        message_parts = []

        if code:
            lang_match = re.match(r"```(\w+)?", code)
            lang_label = (lang_match.group(1).upper() if lang_match and lang_match.group(1) else "CODE")
            message_parts.append(f"📦 *{lang_label}*\n\n{code}")

        if explanation:
            message_parts.append(f"📖 *EXPLANATION*\n\n{explanation}")

        full_message = "\n\n━━━━━━━━━━━━━━━━━━━━━━\n\n".join(message_parts)

        if len(full_message) > 3500:
            full_message = full_message[:3500] + "\n\n... (truncated — ask for more details)"

        try:
            await status.edit_text(full_message, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(full_message, parse_mode="Markdown")

        # Action buttons
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
    if OWNER_ID:
        await app.bot.set_my_commands([
            BotCommand("start", "Open main menu"),
            BotCommand("menu", "Open main menu"),
            BotCommand("lang", "Change language"),
            BotCommand("stats", "Show bot statistics (owner)"),
            BotCommand("broadcast", "Broadcast message (owner)"),
            BotCommand("ban", "Ban a user (owner)"),
            BotCommand("unban", "Unban a user (owner)"),
            BotCommand("blocked", "List blocked users (owner)"),
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
# Force redeploy Sat Oct 10 08:52:29 WAT 2026
