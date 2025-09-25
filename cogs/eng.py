# cogs/eng.py

import nextcord
from nextcord.ext import commands
import sqlite3
import random
import os
import json
import functools
from typing import Optional, List, Dict

import google.generativeai as genai

# --- Local Imports ---
from utils.config import GEMINI_API_KEY
from utils.prompts import (
    CHECK_GRAMMAR_PROMPT,
    DAILY_WORD_EXAMPLE_PROMPT,
    TRANSLATE_PROMPT,
)

# --- Constants ---
DATA_DIR = "db"
DB_PATH = os.path.join(DATA_DIR, "vocabulary.db")
WORDS_PATH = os.path.join(DATA_DIR, "daily_words.json")

# --- Configure the Gemini API client ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("WARNING: GEMINI_API_KEY not found in utils/config.py. AI features will be disabled.")

# --- Decorator to reduce repetitive AI command checks ---
def ai_command_check(func):
    @functools.wraps(func)
    async def wrapper(self, ctx: commands.Context, *args, **kwargs):
        if not self.model:
            await ctx.send("ขออภัยค่ะ ฟีเจอร์ AI ไม่พร้อมใช้งานในขณะนี้ โปรดตรวจสอบการตั้งค่า API key นะคะ")
            return
        async with ctx.typing():
            return await func(self, ctx, *args, **kwargs)
    return wrapper

# --- Cog Class ---
class EnglishLearning(commands.Cog, name="English Learning"):
    """
    A cog for helping users learn English with a friendly female persona named "Ellie".
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.model: Optional[genai.GenerativeModel] = self._initialize_model()
        os.makedirs(DATA_DIR, exist_ok=True)
        self.db_conn = sqlite3.connect(DB_PATH)
        self.db_conn.row_factory = sqlite3.Row 
        self.db_cursor = self.db_conn.cursor()
        self._setup_database()
        self.daily_words_list: List[Dict[str, str]] = self._load_daily_words()

    def _initialize_model(self) -> Optional[genai.GenerativeModel]:
        if not GEMINI_API_KEY: return None
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            print("โมเดล Gemini 'gemini-1.5-flash' โหลดสำเร็จแล้ว (Gemini model loaded successfully).")
            return model
        except Exception as e:
            print(f"ERROR: Could not load Gemini model: {e}")
            return None

    def _setup_database(self):
        self.db_cursor.execute("""
            CREATE TABLE IF NOT EXISTS vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, word TEXT NOT NULL, UNIQUE(user_id, word)
            )
        """)
        self.db_conn.commit()
        print(f"ฐานข้อมูลคำศัพท์พร้อมใช้งานที่: {DB_PATH} (Vocabulary DB is ready).")

    def _load_daily_words(self) -> List[Dict[str, str]]:
        try:
            with open(WORDS_PATH, 'r', encoding='utf-8') as f: return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"WARNING: Could not load {WORDS_PATH}. Creating a default file.")
            default_words = [
                {"eng": "diligent", "thai": "ขยันหมั่นเพียร", "def": "Showing care and conscientiousness in one's work or duties."},
                {"eng": "ubiquitous", "thai": "มีอยู่ทุกหนทุกแห่ง", "def": "Present, appearing, or found everywhere."},
            ]
            with open(WORDS_PATH, 'w', encoding='utf-8') as f: json.dump(default_words, f, indent=4, ensure_ascii=False)
            return default_words

    def cog_unload(self):
        self.db_conn.close()
        print("ปิดการเชื่อมต่อฐานข้อมูลคำศัพท์แล้ว (Vocabulary DB connection closed).")

    async def _call_ai(self, prompt: str) -> Optional[str]:
        if not self.model: return None
        try:
            response = await self.model.generate_content_async(prompt)
            return response.text.strip()
        except Exception as e:
            print(f"AI API Error: {e}")
            return None

    # =========================================================================
    # --- Main English Command Group ---
    # =========================================================================
    
    @commands.group(name="eng", invoke_without_command=True)
    async def eng(self, ctx: commands.Context):
        """
        ชุดคำสั่งสำหรับเรียนรู้ภาษาอังกฤษค่ะ!
        พิมพ์ `!help eng` เพื่อดูคำสั่งทั้งหมดนะคะ
        """
        await ctx.send_help(ctx.command)

    # --- 1. Grammar Checker (Now a subcommand) ---
    @eng.command(
        name="check",
        aliases=["ตรวจไวยากรณ์", "check_grammar"],
        help="ตรวจสอบไวยากรณ์ภาษาอังกฤษด้วย AI | Usage: [p]eng check <english sentence>"
    )
    @ai_command_check
    async def check_grammar(self, ctx: commands.Context, *, sentence: str):
        """Uses Gemini to check English grammar and provide explanations in Thai."""
        prompt = CHECK_GRAMMAR_PROMPT.format(sentence=sentence)
        ai_text = await self._call_ai(prompt)

        if not ai_text:
            await ctx.send("ขออภัยค่ะ เกิดข้อผิดพลาดในการสื่อสารกับ AI ค่ะ")
            return

        embed = nextcord.Embed(title="✔️ ผลการตรวจสอบไวยากรณ์", color=nextcord.Color.blue())
        embed.add_field(name="ประโยคของคุณ", value=f"```{sentence}```", inline=False)

        if "CORRECTED:" in ai_text and "EXPLANATION:" in ai_text:
            try:
                parts = ai_text.split("EXPLANATION:")
                corrected_part = parts[0].replace("CORRECTED:", "").strip()
                explanation_part = parts[1].strip()
                embed.add_field(name="ประโยคที่แก้ไข", value=f"```{corrected_part}```", inline=False)
                embed.add_field(name="คำอธิบาย (จาก AI)", value=explanation_part, inline=False)
                embed.color = nextcord.Color.orange()
            except IndexError:
                 embed.add_field(name="ผลลัพธ์จาก AI", value=f"```\n{ai_text}\n```", inline=False)
                 embed.color = nextcord.Color.light_grey()
        elif ai_text.strip().upper() == 'CORRECT':
            embed.description = "✅ ประโยคของคุณถูกต้องสมบูรณ์แล้วค่ะ! เก่งมากๆ เลยค่ะ"
            embed.color = nextcord.Color.green()
        else:
            embed.add_field(name="ผลลัพธ์จาก AI", value=f"```\n{ai_text}\n```", inline=False)
            embed.color = nextcord.Color.light_grey()
        
        embed.set_footer(text=f"ขับเคลื่อนโดย Google Generative AI | โดย {ctx.author.display_name}")
        await ctx.send(embed=embed)

    # --- 2. Daily Word/Phrase (Now a subcommand) ---
    @eng.command(
        name="word",
        aliases=["คำศัพท์วันนี้", "daily_word"],
        help="สุ่มคำศัพท์ภาษาอังกฤษพร้อมคำแปลและตัวอย่าง | Usage: [p]eng word"
    )
    @ai_command_check
    async def daily_word(self, ctx: commands.Context):
        """Provides a daily word with translation, definition, and an AI-generated example."""
        word_data = random.choice(self.daily_words_list)
        eng_word, thai_meaning, definition = word_data['eng'], word_data['thai'], word_data['def']

        prompt = DAILY_WORD_EXAMPLE_PROMPT.format(eng_word=eng_word)
        example_sentence = await self._call_ai(prompt) or "ไม่สามารถสร้างประโยคตัวอย่างได้ในขณะนี้"
        example_sentence = example_sentence.replace("*", "")

        embed = nextcord.Embed(
            title=f"ศัพท์น่ารู้ประจำวัน: {eng_word.title()}",
            description=f"**{definition}**",
            color=nextcord.Color.purple()
        )
        embed.add_field(name="ความหมายภาษาไทย", value=thai_meaning, inline=True)
        embed.add_field(name="ประโยคตัวอย่าง (จาก AI)", value=f"```{example_sentence}```", inline=False)
        # Updated footer to reflect new command structure
        embed.set_footer(text=f"ใช้ {ctx.prefix}eng vocab save {eng_word} เพื่อบันทึกคำนี้!")
        await ctx.send(embed=embed)

    # --- 3. Translation Assistant (Now a subcommand) ---
    @eng.command(name="translate", aliases=["แปล"])
    @ai_command_check
    async def translate(self, ctx: commands.Context, *, text_to_translate: str):
        """แปลข้อความระหว่างไทยและอังกฤษด้วย AI"""
        prompt = TRANSLATE_PROMPT.format(text_to_translate=text_to_translate)
        translated_text = await self._call_ai(prompt)

        if not translated_text:
            await ctx.send("ขออภัยค่ะ เกิดข้อผิดพลาดในการแปลภาษาค่ะ")
            return

        embed = nextcord.Embed(title="🌐 ผลการแปลภาษา", color=nextcord.Color.dark_teal())
        embed.add_field(name="ข้อความต้นฉบับ", value=f"```{text_to_translate}```", inline=False)
        embed.add_field(name="คำแปล (จาก AI)", value=f"```{translated_text}```", inline=False)
        embed.set_footer(text=f"ขับเคลื่อนโดย Google Generative AI | โดย {ctx.author.display_name}")
        await ctx.send(embed=embed)

    # --- 4. Personal Vocabulary Builder (Now a nested subcommand group) ---
    @eng.group(name="vocab", invoke_without_command=True, aliases=["คลังศัพท์"])
    async def vocab(self, ctx: commands.Context):
        """จัดการคลังคำศัพท์ส่วนตัวของคุณ (ใช้ !eng vocab list หรือ !eng vocab save)"""
        await ctx.send_help(ctx.command)

    @vocab.command(name="save", aliases=["บันทึก"])
    async def save_word(self, ctx: commands.Context, *, word: str):
        """บันทึกคำศัพท์ลงในคลังส่วนตัวของคุณ"""
        user_id = ctx.author.id
        clean_word = word.lower().strip()
        if not clean_word:
            await ctx.send("กรุณาระบุคำศัพท์ที่ต้องการบันทึกด้วยค่ะ")
            return
        
        try:
            self.db_cursor.execute("INSERT INTO vocabulary (user_id, word) VALUES (?, ?)", (user_id, clean_word))
            self.db_conn.commit()
            embed = nextcord.Embed(
                title="📖 บันทึกคำศัพท์สำเร็จ!",
                description=f"บันทึกคำว่า `{clean_word}` ลงในคลังศัพท์ส่วนตัวของคุณเรียบร้อยแล้วค่ะ",
                color=nextcord.Color.green()
            )
            # Updated footer
            embed.set_footer(text=f"ใช้ {ctx.prefix}eng vocab list เพื่อดูคำศัพท์ทั้งหมด")
            await ctx.send(embed=embed)
        except sqlite3.IntegrityError:
            await ctx.send(f"⚠️ คุณเคยบันทึกคำว่า `{clean_word}` ไปแล้วค่ะ")
        except sqlite3.Error as e:
            await ctx.send(f"เกิดข้อผิดพลาดกับฐานข้อมูลค่ะ: `{e}`")

    @vocab.command(name="list", aliases=["show", "ดู"])
    async def list_vocab(self, ctx: commands.Context):
        """แสดงคำศัพท์ทั้งหมดที่คุณบันทึกไว้"""
        user_id = ctx.author.id
        self.db_cursor.execute("SELECT word FROM vocabulary WHERE user_id = ? ORDER BY word", (user_id,))
        words = [row['word'] for row in self.db_cursor.fetchall()]

        if not words:
            await ctx.send(f"คุณยังไม่มีคำศัพท์ที่บันทึกไว้เลย ลองใช้ `{ctx.prefix}eng vocab save <word>` ดูสิคะ!")
            return

        description = "\n".join(f"• {word}" for word in words)
        embed = nextcord.Embed(
            title=f"คลังคำศัพท์ของ {ctx.author.display_name}",
            description=description,
            color=nextcord.Color.dark_purple()
        )
        await ctx.send(embed=embed)


def setup(bot: commands.Bot):
    """Adds the EnglishLearning cog to the bot."""
    if not GEMINI_API_KEY:
        print("Could not load 'EnglishLearning' cog: GEMINI_API_KEY is not set.")
        return
    bot.add_cog(EnglishLearning(bot))