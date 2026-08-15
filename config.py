"""
Ryhavean Userbot — Konfiqurasiya / Configuration (Telethon)
───────────────────────────────────────────────────────────
Bütün ENV dəyişənləri, verilənlər bazası və qlobal vəziyyət burada saxlanılır.
"""

import os
import time
import logging
from collections import defaultdict

import certifi
import pymongo
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── Telegram API ────────────────────────────────────────────────────────────
raw_api_id = os.getenv('API_ID', '').strip()
API_ID = int(raw_api_id) if raw_api_id.isdigit() else 0
API_HASH = os.getenv('API_HASH', '')

# Telethon string session (userbot)
SESSION_STR = os.getenv('SESSION_STR', '') or os.getenv('STRING_SESSION', '')

# @BotFather token (köməkçi bot — inline / düymələr / yükləmələr üçün)
BOT_TOKEN = os.getenv('BOT_TOKEN', '')

# ── AI gateway (Anthropic-uyğun) ────────────────────────────────────────────
AI_API_KEY = os.getenv('AI_API_KEY', '')
AI_BASE_URL = os.getenv('AI_BASE_URL', '').rstrip('/')
AGENT_MODEL = os.getenv('AGENT_MODEL', 'claude-opus-4-8')
AGENT_VISION_MODEL = os.getenv('AGENT_VISION_MODEL', 'claude-opus-4-8')
AGENT_MAX_TOKENS = int(os.getenv('AGENT_MAX_TOKENS', '2048'))

AGENT_TOOL_TIMEOUT = int(os.getenv('AGENT_TOOL_TIMEOUT', '60'))
AGENT_MAX_OUTPUT_CHARS = int(os.getenv('AGENT_MAX_OUTPUT_CHARS', '6000'))
AGENT_MAX_ITERATIONS = int(os.getenv('AGENT_MAX_ITERATIONS', '12'))
AGENT_MAX_HISTORY = int(os.getenv('AGENT_MAX_HISTORY', '20'))
AGENT_AUTO_COMPACT = os.getenv('AGENT_AUTO_COMPACT', 'true').lower() in ('true', '1', 'yes')
AGENT_COMPACT_THRESHOLD = int(os.getenv('AGENT_COMPACT_THRESHOLD', '14'))

AGENT_USE_CHEAPEST_MODEL = os.getenv('AGENT_USE_CHEAPEST_MODEL', 'false').lower() in ('true', '1', 'yes')
AGENT_PRICING_API_URL = os.getenv(
    'AGENT_PRICING_API_URL',
    f'{AI_BASE_URL}/api/pricing' if AI_BASE_URL else '',
)
AGENT_MODEL_CACHE_TTL = int(os.getenv('AGENT_MODEL_CACHE_TTL', '3600'))

AGENT_ALLOW_SHELL = os.getenv('AGENT_ALLOW_SHELL', 'false').lower() in ('true', '1', 'yes')
AGENT_ALLOW_MODERATION = os.getenv('AGENT_ALLOW_MODERATION', 'false').lower() in ('true', '1', 'yes')
AGENT_ALLOW_TELEGRAM_API = os.getenv('AGENT_ALLOW_TELEGRAM_API', 'false').lower() in ('true', '1', 'yes')

# ── YouTube / yt-dlp ────────────────────────────────────────────────────────
YT_DLP_API_KEY = os.getenv('YT_DLP_API_KEY', '')
YT_DLP_BASE_URL = os.getenv('YT_DLP_BASE_URL', '')

# ── Verilənlər bazası / storage ─────────────────────────────────────────────
MONGO_URI = os.getenv('MONGO_URI', '')
DB_NAME = os.getenv('DB_NAME', 'userbot')

from storage import MemoryCollection, SqliteCollection  # noqa: E402

STORAGE_BACKEND = os.getenv('STORAGE_BACKEND', '').strip().lower()
SQLITE_PATH = os.getenv('SQLITE_PATH', os.path.join(os.getcwd(), 'data', 'sessions.db'))


def _init_storage():
    backend = STORAGE_BACKEND or ('mongo' if MONGO_URI else 'memory')
    if backend == 'mongo':
        try:
            client = pymongo.MongoClient(
                MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000
            )
            client.admin.command("ping")
            logger.info("MongoDB qoşuldu / connected (database: %s)", DB_NAME)
            return client, client[DB_NAME]["user_sessions"]
        except Exception as e:
            logger.warning(
                "MongoDB qoşulmadı (%s); yaddaş rejiminə keçilir / falling back to memory.", e
            )
            return None, MemoryCollection()
    if backend == 'sqlite':
        logger.info("SQLite storage: %s", SQLITE_PATH)
        return None, SqliteCollection(SQLITE_PATH)
    logger.info("Yaddaş (in-memory) storage — restartda məlumat itir.")
    return None, MemoryCollection()


mongo_client, user_sessions = _init_storage()
db = mongo_client[DB_NAME] if mongo_client else None

# ── Dil / i18n ──────────────────────────────────────────────────────────────
from languages import init_language_manager  # noqa: E402

lang_manager = init_language_manager(user_sessions)
DEFAULT_LANG = (os.getenv('DEFAULT_LANG', 'az') or 'az').lower()
if DEFAULT_LANG not in ('az', 'tr', 'en'):
    DEFAULT_LANG = 'az'

# ── Əmr prefiksləri ─────────────────────────────────────────────────────────
HARDCODED_PREFIXES = ["!", ".", "?", "^", "_"]

admin_file = os.path.join(os.getcwd(), "data", "admins.txt")

# ── Qlobal vəziyyət / global state ──────────────────────────────────────────
clients = {}
apps = {}
conversations = {}
chat_queues = {}
active_streams = {}
last_response_time = {}
used_words = {}
active = {}
songs_client = {}
IGNORE_DURATION = 5
StartTime = time.time()

SUDO = defaultdict(list)

from fonts import *  # noqa: F401,F403,E402

# ── Kanal / qrup ────────────────────────────────────────────────────────────
GROUP = os.getenv('GROUP', 'RyhaveanTeam')
CHANNEL = os.getenv('CHANNEL', 'ryhaveanupdates')
TEAM_CHANNEL = os.getenv('TEAM_CHANNEL', 'RyhaveanTeam')
UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL', 'ryhaveanupdates')

BOT_NAME = "Ryhavean Userbot"
BOT_VERSION = "2.0.0"

# ── Xarici plaginlər ────────────────────────────────────────────────────────
EXTRA_PLUGINS_DIR = os.getenv('EXTRA_PLUGINS_DIR', os.path.join(os.getcwd(), 'plugins'))
loaded_extra_plugins = []
