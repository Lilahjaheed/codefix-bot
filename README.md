# CodeFix Bot

A Telegram bot that solves coding problems in Python, JavaScript, Java, React, and HTML/CSS — powered by Google Gemini (free tier).

## Setup

1. Create bot via @BotFather → get `BOT_TOKEN`
2. Get free API key from https://aistudio.google.com → `GEMINI_API_KEY`
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run:
   ```bash
   export BOT_TOKEN="your_token"
   export GEMINI_API_KEY="your_key"
   python bot.py
   ```

## Deploy (Free)

### Render.com
1. Push this folder to GitHub
2. Create new Web Service on Render
3. Build command: `pip install -r requirements.txt`
4. Start command: `python bot.py`
5. Add env vars: `BOT_TOKEN`, `GEMINI_API_KEY`
6. Deploy

## Cost: $0
- Telegram Bot API: free, unlimited users
- Gemini API: 1,500 requests/day free
