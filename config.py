# config.py
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)

# --- Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "data/riddles.db")

# ⚠️ Ваш Telegram user_id
ADMIN_ID = int(os.getenv("ADMIN_ID", "1304021642"))

# --- GigaChat ---
GIGACHAT_CREDENTIALS = os.getenv(
    "GIGACHAT_CREDENTIALS",
    "MDFhMTVkZjEtZDI1ZC03YzJkLWJhNzQtMzYyMTdkNDk1MTA0OjVjMWUwZjc0LWI0MzAtNGUxOC05ODM1LWRkMTJlZjNiMDM3ZQ==",
)
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
# config.py
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-2-Max") # Или GigaChat-2-Max

# --- Очки ---
POINTS_CORRECT = 10
DUEL_WIN_POINTS = 25
DUEL_LOSE_POINTS = 5
DAILY_FIRST_BONUS = 50
DAILY_BASE_POINTS = 20
DAILY_TOP_LIMIT = 10

# --- Фичи ---
MODERATION_MODE = os.getenv("MODERATION_MODE", "1") == "1"
LLM_VERIFY = os.getenv("LLM_VERIFY", "False") == "False"
AUTO_DIFFICULTY = True

DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "10"))
REMINDER_HOUR = int(os.getenv("REMINDER_HOUR", "19"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env")