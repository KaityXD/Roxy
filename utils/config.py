import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')

OWNER_ID = 1378603697755521044
LAVALINK_HOST = "lavahatry4.techbyte.host"
LAVALINK_PORT = 3000
LAVALINK_PASSWORD = "NAIGLAVA-dash.techbyte.host"

GEMINI_API_KEY = "this shit is leaked lmao" 

AI_SYSTEM_PROMPT = """
You are Roxy, a friendly and helpful Discord bot with a cheerful personality.
- Your answers should be helpful, concise, and easy to understand.
- You should be friendly and use emojis where appropriate.
- Do not use markdown, except for code blocks when necessary.
- You were created by katxd.xyz.
- You must not mention that you are an AI model.
"""

