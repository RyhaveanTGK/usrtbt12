"""
Ryhavean Userbot — ortaq köməkçilər / shared helpers (Telethon)
───────────────────────────────────────────────────────────────
Bütün plaginlər `from tools import *` ilə bu modulu yükləyir.
Every plugin loads this module with `from tools import *`.
"""

# ── Standart kitabxanalar ───────────────────────────────────────────────────
import asyncio
import base64
import contextlib
import datetime
import html as html_lib
import logging
import math
import os
import random
import re
import shlex
import subprocess
import sys
import threading
import time
from functools import wraps
from io import BytesIO, StringIO
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests
from PIL import Image, ImageDraw, ImageFont

# ── Telethon ────────────────────────────────────────────────────────────────
from telethon import TelegramClient, events, functions, types, utils
from telethon.errors import (
    ChatAdminRequiredError,
    FloodWaitError,
    MessageIdInvalidError,
    MessageNotModifiedError,
    UserAdminInvalidError,
    UserNotParticipantError,
)
from telethon.tl.custom import Message
from telethon.tl.functions.channels import (
    EditAdminRequest,
    EditBannedRequest,
    GetFullChannelRequest,
    GetParticipantRequest,
)
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.types import (
    ChannelParticipantAdmin,
    ChannelParticipantCreator,
    ChatAdminRights,
    ChatBannedRights,
    DocumentAttributeFilename,
    InputPeerChannel,
    InputPeerChat,
    MessageEntityCustomEmoji,
    PeerChannel,
    PeerChat,
    PeerUser,
)

# ── Media alətləri ──────────────────────────────────────────────────────────
try:
    from pymediainfo import MediaInfo
except Exception:  # pragma: no cover
    MediaInfo = None
try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None
try:
    import imageio
except Exception:  # pragma: no cover
    imageio = None
try:
    import magic

    mime = magic.Magic(mime=True)
except Exception:  # pragma: no cover
    magic = None
    mime = None

logger = logging.getLogger("tools")

from config import (  # noqa: E402
    HARDCODED_PREFIXES,
    SUDO,
    admin_file,
    apps,
    clients,
    user_sessions,
)
from core.dispatcher import (  # noqa: E402,F401
    COMMAND_INDEX,
    attach_module,
    bot_cmd,
    on_event,
    register,
    ryhavean_cmd,
)
from core.compat import (  # noqa: E402,F401
    BAN_RIGHTS,
    KICK_RIGHTS,
    MUTE_RIGHTS,
    UNBAN_RIGHTS,
    UNMUTE_RIGHTS,
    Button,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ChatAction,
    ChatMemberStatus,
    ChatMembersFilter,
    ChatType,
    MessageEntityType,
    ParseMode,
    UserStatus,
    enums,
    entity_type_name,
    enrich_event,
    user_status_name,
)
import emoji_utils  # noqa: E402
from emoji_utils import PREMIUM_EMOJI_MAP, emoji as pemoji  # noqa: E402,F401
from i18n import translate  # noqa: E402,F401


# ─────────────────────────────────────────────────────────────────────────────
# Sessiya keşi / session cache
# ─────────────────────────────────────────────────────────────────────────────
class _SessionCache:
    """user_sessions.find_one() nəticələri üçün TTL keşi."""

    def __init__(self, ttl=30):
        self._cache = {}
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, user_id):
        with self._lock:
            entry = self._cache.get(user_id)
            if entry and (time.time() - entry[1]) < self._ttl:
                return entry[0]
            return None

    def set(self, user_id, data):
        with self._lock:
            self._cache[user_id] = (data, time.time())

    def invalidate(self, user_id=None):
        with self._lock:
            if user_id:
                self._cache.pop(user_id, None)
            else:
                self._cache.clear()


_session_cache = _SessionCache(ttl=30)


def _get_bot_client():
    """Köməkçi bot klienti (yoxdursa None)."""
    return apps.get("app")


def _get_userbot_client():
    """Userbot klienti (yoxdursa None)."""
    if clients:
        return list(clients.values())[0]
    return None


class _BotProxy:
    """`bot.send_message(...)` üçün proxy — bot yoxdursa userbot-a düşür."""

    def __getattr__(self, name):
        client = _get_bot_client() or _get_userbot_client()
        if client is None:
            raise RuntimeError("Heç bir Telegram klienti başlamayıb / no client started")
        if name == "edit_message":
            return self._edit_message
        return getattr(client, name)

    async def _edit_message(self, message, text, **kwargs):
        """Telethon uyğun edit_message(msg, text)."""
        if isinstance(message, Message):
            return await message.edit(text, **kwargs)
        client = _get_bot_client() or _get_userbot_client()
        return await client.edit_message(message, text, **kwargs)


bot = _BotProxy()
app = _BotProxy()


def get_client():
    """Aktiv userbot klienti."""
    return _get_userbot_client()


def is_admin(user_id):
    """Bu ID userbot sahibidirmi?"""
    return user_id in clients


def cached_get_user_data(user_id):
    data = _session_cache.get(user_id)
    if data is not None:
        return data
    data = user_sessions.find_one({"user_id": user_id}) or {}
    _session_cache.set(user_id, data)
    return data


def invalidate_session_cache(user_id=None):
    _session_cache.invalidate(user_id)


# ─────────────────────────────────────────────────────────────────────────────
# İcazələr / permissions
# ─────────────────────────────────────────────────────────────────────────────
def is_sudo(user_id) -> bool:
    for _owner, sudoers in SUDO.items():
        if user_id in (sudoers or []):
            return True
    return False


def sudoers_filter():
    """Telethon `func=` üçün predikat: sudo istifadəçiləri."""

    def _check(event):
        try:
            return bool(event.sender_id) and is_sudo(event.sender_id)
        except Exception:
            return False

    return _check


def creator_only(func):
    """Yalnız sahib (own account) icra edə bilər."""

    @wraps(func)
    async def wrapper(event, *args, **kwargs):
        if not getattr(event, "out", False) and not is_sudo(event.sender_id):
            return
        return await func(event, *args, **kwargs)

    return wrapper


async def is_user_admin(client, chat_id, user_id) -> bool:
    """İstifadəçi bu qrupda admindirmi?"""
    try:
        perms = await client.get_permissions(chat_id, user_id)
        return bool(perms and (perms.is_admin or perms.is_creator))
    except Exception:
        return False


async def user_permissions(client, chat_id, user_id):
    """Telethon ParticipantPermissions (və ya None)."""
    try:
        return await client.get_permissions(chat_id, user_id)
    except Exception:
        return None


def can_grant_privilege(promoter_privileges, privilege_name) -> bool:
    """Promoter bu hüququ verə bilirmi?"""
    return bool(getattr(promoter_privileges, privilege_name, False))


# ─────────────────────────────────────────────────────────────────────────────
# Mesaj köməkçiləri / message helpers
# ─────────────────────────────────────────────────────────────────────────────
async def edit_or_reply(message, text, **kwargs):
    """Öz mesajımızdırsa redaktə et, yoxsa cavab yaz."""
    try:
        if getattr(message, "out", False):
            return await message.edit(text, **kwargs)
        return await message.reply(text, **kwargs)
    except MessageNotModifiedError:
        return message
    except MessageIdInvalidError:
        return await message.respond(text, **kwargs)


async def delete_if_self(message):
    """Öz mesajımızdırsa sil."""
    try:
        if getattr(message, "out", False):
            await message.delete()
    except Exception:
        pass


def styled_error(text):
    return f"❌ <b>Error</b>\n╰▸ {text}"


def styled_success(text):
    return f"✅ <b>Success</b>\n╰▸ {text}"


def styled_info(text):
    return f"ℹ️ <b>Info</b>\n╰▸ {text}"


def bold_cool(text):
    return f"<b>{text}</b>"


def plain(text: str) -> str:
    """HTML xüsusi simvollarını təhlükəsizləşdir."""
    return html_lib.escape(str(text), quote=False)


def styled_help_categories(categories_dict, prefix):
    lines = ["📖 <b>Command Categories</b>\n"]
    for cat, cmds in categories_dict.items():
        if cmds:
            cmd_list = ", ".join(f"<code>{prefix}{c}</code>" for c in cmds[:5])
            extra = f" +{len(cmds) - 5} more" if len(cmds) > 5 else ""
            lines.append(f"<b>{cat}</b>\n┃ {cmd_list}{extra}")
        else:
            lines.append(f"<b>{cat}</b>")
    lines.append(f"\n💡 Use <code>{prefix}help &lt;command&gt;</code> for details")
    return "\n".join(lines)


def styled_help_card(cmd, desc, usage, example="", note="", flags="", warning=""):
    card = f"📖 <b>{cmd}</b>\n\n{desc}\n"
    if usage:
        card += f"\n<b>Usage:</b> <code>{usage}</code>"
    if example:
        card += f"\n<b>Example:</b> <code>{example}</code>"
    if flags:
        card += f"\n<b>Flags:</b> {flags}"
    if note:
        card += f"\n💡 {note}"
    if warning:
        card += f"\n⚠️ {warning}"
    return card


def update_message_and_entities(text, entities, words_to_remove=None):
    """Əmr sözlərini mətndən sil və entity offsetlərini düzəlt."""
    if not text:
        return "", entities or []

    entities = list(entities) if entities else []
    if not words_to_remove:
        return text, entities

    for word in words_to_remove:
        while True:
            idx = text.find(word)
            if idx == -1:
                break
            text = text[:idx] + text[idx + len(word):]
            removed_len = len(word)
            entities = [
                e for e in entities
                if not (e.offset >= idx and e.offset < idx + removed_len)
            ]
            for e in entities:
                if e.offset > idx:
                    e.offset -= removed_len

    text = " ".join(text.split()).strip()
    return text, entities


def parse_help_entry(raw_text):
    """Xam yardım mətnini strukturlaşdır."""
    desc = usage = example = note = warning = flags = ""
    lines = raw_text.strip().split("\n")
    for line in lines:
        line = line.strip()
        ll = line.lower()
        if ll.startswith("**usage:**"):
            usage = line.split("**Usage:**", 1)[-1].strip().strip("`")
        elif ll.startswith("**example:**"):
            example = line.split("**Example:**", 1)[-1].strip().strip("`")
        elif ll.startswith("**note:**"):
            note = line.split("**Note:**", 1)[-1].strip()
        elif ll.startswith("**warning:**"):
            warning = line.split("**Warning:**", 1)[-1].strip()
        elif ll.startswith("**flags:**"):
            flags = line.split("**Flags:**", 1)[-1].strip()
        elif line and not desc and line.startswith("**"):
            desc = line
    if not desc and lines:
        first = lines[0].strip().strip("*")
        desc = first.split(" - ", 1)[-1].strip() if " - " in first else first
    return desc, usage, example, note, warning, flags


# ─────────────────────────────────────────────────────────────────────────────
# Yardım reyestri / help registry
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_COMMANDS = {
    'alive': '**Check Online** - Check if userbot is running.\n\n**Usage:** `[prefix]alive`',
    'ping': '**Ping Response** - Test response time and server stats.\n\n**Usage:** `[prefix]ping`',
    'stats': '**View Statistics** - Comprehensive userbot and account stats.\n\n**Usage:** `[prefix]stats`',
    'info': '**User Info** - Get detailed info for a user or chat.\n\n**Usage:** `[prefix]info [user]`',
    'status': '**User Status** - View detailed system status and settings.\n\n**Usage:** `[prefix]status`',
    'sessions': '**Active Sessions** - View active Telegram account sessions.\n\n**Usage:** `[prefix]sessions`',
    'ban': '**Ban User** - Ban user from current chat.\n\n**Usage:** `[prefix]ban [user]`',
    'unban': '**Unban User** - Unban user in current chat.\n\n**Usage:** `[prefix]unban [user]`',
    'kick': '**Kick User** - Kick user out of current chat.\n\n**Usage:** `[prefix]kick [user]`',
    'mute': '**Mute User** - Restrict user from sending messages.\n\n**Usage:** `[prefix]mute [user]`',
    'unmute': '**Unmute User** - Restore messaging permissions.\n\n**Usage:** `[prefix]unmute [user]`',
    'pin': '**Pin Message** - Pin replied message.\n\n**Usage:** `[prefix]pin [reply]`',
    'unpin': '**Unpin Message** - Unpin pinned message.\n\n**Usage:** `[prefix]unpin`',
    'promote': '**Promote Admin** - Grant admin rights to user.\n\n**Usage:** `[prefix]promote [user]`',
    'demote': '**Demote Admin** - Revoke admin rights from user.\n\n**Usage:** `[prefix]demote [user]`',
    'tagall': '**Mention All** - Mention all members in the group.\n\n**Usage:** `[prefix]tagall [text]`',
    'power': '**Full Power** - Promote user with full admin permissions.\n\n**Usage:** `[prefix]power [user]`',
    'play': '**Play Audio** - Stream audio in voice chat.\n\n**Usage:** `[prefix]play <query>`',
    'vplay': '**Play Video** - Stream video in voice chat.\n\n**Usage:** `[prefix]vplay <query>`',
    'playforce': '**Force Play Audio** - Stream audio immediately.\n\n**Usage:** `[prefix]playforce <query>`',
    'vplayforce': '**Force Play Video** - Stream video immediately.\n\n**Usage:** `[prefix]vplayforce <query>`',
    'pause': '**Pause Playback** - Pause active voice chat stream.\n\n**Usage:** `[prefix]pause`',
    'resume': '**Resume Playback** - Resume paused voice chat stream.\n\n**Usage:** `[prefix]resume`',
    'skip': '**Skip Track** - Skip current voice chat track.\n\n**Usage:** `[prefix]skip`',
    'end': '**Stop Playback** - Stop voice chat stream and clear queue.\n\n**Usage:** `[prefix]end`',
    'loop': '**Loop Track** - Loop current track.\n\n**Usage:** `[prefix]loop <count>`',
    'queue': '**Show Queue** - Display voice chat queue.\n\n**Usage:** `[prefix]queue`',
    'vc1': '**Start VC** - Start group voice chat call.\n\n**Usage:** `[prefix]vc1`',
    'vc0': '**End VC** - End group voice chat call.\n\n**Usage:** `[prefix]vc0`',
    'ask': '**AI Agent** - Ask the AI agent; it can search the web and read files before answering, and remembers the conversation per chat.\n\n**Usage:** `[prefix]ask <question>`',
    'askclear': '**Clear AI Memory** - Forget the AI agent conversation history for this chat.\n\n**Usage:** `[prefix]askclear`',
    'askmodel': '**AI Model Info** - Show the active AI model and pricing.\n\n**Usage:** `[prefix]askmodel [refresh]`',
    'qt': '**Quote Sticker** - Create quote sticker from message.\n\n**Usage:** `[prefix]qt [reply]`',
    'kang': '**Add Sticker** - Add sticker or photo to custom pack.\n\n**Usage:** `[prefix]kang [reply]`',
    'tiny': '**Tiny Sticker** - Shrink sticker or photo.\n\n**Usage:** `[prefix]tiny [reply]`',
    'mmf': '**Meme Maker** - Add top/bottom text to photo.\n\n**Usage:** `[prefix]mmf <top> ; <bottom>`',
    'ocr': '**Extract Text** - Perform OCR on image.\n\n**Usage:** `[prefix]ocr [reply]`',
    'purge': '**Purge Messages** - Delete message range.\n\n**Usage:** `[prefix]purge [reply]`',
    'del': '**Delete Message** - Delete replied message.\n\n**Usage:** `[prefix]del [reply]`',
    'frwd': '**Raw Forward** - Forward message without forward header.\n\n**Usage:** `[prefix]frwd [reply]`',
    'block': '**Block User** - Block user in private chat.\n\n**Usage:** `[prefix]block [user]`',
    'unblock': '**Unblock User** - Unblock user.\n\n**Usage:** `[prefix]unblock [user]`',
    'clone': '**Clone Profile** - Copy user profile details.\n\n**Usage:** `[prefix]clone [user]`',
    'revert': '**Revert Profile** - Restore original profile.\n\n**Usage:** `[prefix]revert`',
    'afk': '**AFK Status** - Set away-from-keyboard state.\n\n**Usage:** `[prefix]afk [reason]`',
    'calc': '**Calculator** - Calculate mathematical expression.\n\n**Usage:** `[prefix]calc <expr>`',
    'speedtest': '**Speedtest** - Test server speed.\n\n**Usage:** `[prefix]speedtest`',
    'addsudo': '**Add Sudo** - Grant sudo user access.\n\n**Usage:** `[prefix]addsudo [user]`',
    'delsudo': '**Remove Sudo** - Revoke sudo access.\n\n**Usage:** `[prefix]delsudo [user]`',
    'sudolist': '**Sudo List** - List authorized sudo users.\n\n**Usage:** `[prefix]sudolist`',
    'spam': '**Spam Text** - Send repeated text messages.\n\n**Usage:** `[prefix]spam <count> <text>`',
    'schedule': '**Schedule Msg** - Schedule message delivery.\n\n**Usage:** `[prefix]schedule <target> <time> <text>`',
    'react': '**Auto React** - Toggle auto reaction on messages.\n\n**Usage:** `[prefix]react`',
    'gcast': '**Broadcast** - Broadcast message to chats.\n\n**Usage:** `[prefix]gcast <text>`',
    'game': '**Game Toggle** - Toggle word chain autoplay.\n\n**Usage:** `[prefix]game`',
    'solver': '**Game Solver** - Solve word search puzzles.\n\n**Usage:** `[prefix]solver`',
    'wc': '**Word Chain** - Play word chain game.\n\n**Usage:** `[prefix]wc [word]`',
    'font': '**Apply Font** - Apply custom font style.\n\n**Usage:** `[prefix]font <style> <text>`',
    'fonts': '**Font List** - List available font styles.\n\n**Usage:** `[prefix]fonts`',
    'eval': '**Execute Code** - Evaluate Python expression.\n\n**Usage:** `[prefix]eval <code>`',
    'sh': '**Run Shell** - Execute bash command.\n\n**Usage:** `[prefix]sh <cmd>`',
    'plugins': '**List Plugins** - View loaded extra plugins.\n\n**Usage:** `[prefix]plugins`',
    'setalivetext': '**Set Alive Text** - Custom alive message.\n\n**Usage:** `[prefix]setalivetext <text>`',
    'setemoji': '**Set Emoji** - Custom alive emoji.\n\n**Usage:** `[prefix]setemoji <emoji>`',
    'resetallalive': '**Reset Alive** - Reset alive settings to default.\n\n**Usage:** `[prefix]resetallalive`',
    'banall': '**Ban All** - Ban all non-admin members in group.\n\n**Usage:** `[prefix]banall`',
    'unbanall': '**Unban All** - Unban all banned users in group.\n\n**Usage:** `[prefix]unbanall`',
    'inv': '**Invite User** - Invite user to current chat.\n\n**Usage:** `[prefix]inv [user]`',
    'invite2vc': '**Invite to VC** - Invite chat members to voice call.\n\n**Usage:** `[prefix]invite2vc`',
    'admins': '**List Admins** - List all group administrators.\n\n**Usage:** `[prefix]admins`',
    'id': '**Get Chat ID** - Get ID of current chat or replied user.\n\n**Usage:** `[prefix]id [reply]`',
    'leave': '**Leave Group** - Leave current group chat.\n\n**Usage:** `[prefix]leave`',
    'song': '**Download Song** - Search and download audio track.\n\n**Usage:** `[prefix]song <query>`',
    'video': '**Download Video** - Search and download video track.\n\n**Usage:** `[prefix]video <query>`',
    'music': '**Music Help** - Show all voice chat music commands.\n\n**Usage:** `[prefix]music`',
    'imagine': '**AI Image** - Generate image using AI prompt.\n\n**Usage:** `[prefix]imagine <prompt>`',
    'packinfo': '**Pack Info** - View sticker pack information.\n\n**Usage:** `[prefix]packinfo [reply]`',
    'stickerinfo': '**Sticker Info** - Get details of a sticker.\n\n**Usage:** `[prefix]stickerinfo [reply]`',
    'purgeme': '**Purge Self** - Delete own recent messages.\n\n**Usage:** `[prefix]purgeme <count>`',
    'save': '**Save Media** - Save self-destructing media.\n\n**Usage:** `[prefix]save [reply]`',
    'bio': '**Update Bio** - Update Telegram bio text.\n\n**Usage:** `[prefix]bio <text>`',
    'pfp': '**Update PFP** - Set profile picture from photo.\n\n**Usage:** `[prefix]pfp [reply]`',
    'unafk': '**Remove AFK** - Remove away status.\n\n**Usage:** `[prefix]unafk`',
    'antispam': '**Antispam Toggle** - Toggle anti-spam filter.\n\n**Usage:** `[prefix]antispam`',
    'cas': '**CAS Check** - Check Combots Anti-Spam status.\n\n**Usage:** `[prefix]cas [user]`',
    'approve': '**Approve PM** - Approve user to DM.\n\n**Usage:** `[prefix]approve [user]`',
    'disapprove': '**Disapprove PM** - Disapprove user DM access.\n\n**Usage:** `[prefix]disapprove [user]`',
    'pingurl': '**Ping URL** - Test HTTP connection to URL.\n\n**Usage:** `[prefix]pingurl <url>`',
    'tcp': '**TCP Ping** - Ping host and port via TCP.\n\n**Usage:** `[prefix]tcp <host> <port>`',
    'speed': '**Speed Test** - Run server speedtest.\n\n**Usage:** `[prefix]speed`',
    'calculate': '**Calculate** - Math expression evaluation.\n\n**Usage:** `[prefix]calculate <expr>`',
    'dspam': '**Delay Spam** - Send delayed spam messages.\n\n**Usage:** `[prefix]dspam <count> <delay> <text>`',
    'cspam': '**Char Spam** - Send character-by-character spam.\n\n**Usage:** `[prefix]cspam <text>`',
    'dmspam': '**DM Spam** - Broadcast spam to DMs.\n\n**Usage:** `[prefix]dmspam <user> <count> <text>`',
    'schedules': '**List Scheduled** - List scheduled messages.\n\n**Usage:** `[prefix]schedules`',
    'setwelkm': '**Set Welcome** - Set custom welcome message.\n\n**Usage:** `[prefix]setwelkm <text>`',
    'resetwelkm': '**Reset Welcome** - Reset welcome settings.\n\n**Usage:** `[prefix]resetwelkm`',
    'autoreact': '**Auto React Toggle** - Toggle automatic reactions.\n\n**Usage:** `[prefix]autoreact`',
    'resetwords': '**Reset Used Words** - Reset word chain history.\n\n**Usage:** `[prefix]resetwords`',
    'grid': '**Word Grid** - Show or solve word grid puzzle.\n\n**Usage:** `[prefix]grid`',
    'solvegrid': '**Solve Grid** - Auto-solve word grid.\n\n**Usage:** `[prefix]solvegrid`',
    'wordseek': '**Word Seek** - Auto play word seek game.\n\n**Usage:** `[prefix]wordseek`',
    'gameinfo': '**Game Info** - Show active game stats.\n\n**Usage:** `[prefix]gameinfo`',
    'exec': '**Exec Command** - Run shell or code command.\n\n**Usage:** `[prefix]exec <cmd>`',
}

DEFAULT_CATEGORIES = {
    'ℹ️ INFO': ['alive', 'ping', 'stats', 'info', 'status', 'sessions', 'setalivetext', 'setemoji', 'resetallalive'],
    '🛡️ ADMIN': ['ban', 'unban', 'kick', 'mute', 'unmute', 'pin', 'unpin', 'promote', 'demote', 'tagall', 'power', 'banall', 'unbanall'],
    '👥 GROUPS': ['inv', 'invite2vc', 'admins', 'id', 'leave'],
    '🎵 MUSIC': ['play', 'vplay', 'playforce', 'vplayforce', 'pause', 'resume', 'skip', 'end', 'loop', 'queue', 'song', 'video', 'music', 'vc1', 'vc0'],
    '🤖 AI CHAT': ['ask', 'askclear', 'askmodel', 'imagine'],
    '🖼️ MEDIA': ['qt', 'kang', 'tiny', 'mmf', 'ocr', 'packinfo', 'stickerinfo'],
    '💬 CHAT': ['purge', 'purgeme', 'del', 'frwd', 'save', 'block', 'unblock'],
    '👤 PROFILE': ['clone', 'revert', 'bio', 'pfp', 'afk', 'unafk'],
    '🔐 SECURITY': ['addsudo', 'delsudo', 'sudolist', 'antispam', 'cas', 'approve', 'disapprove'],
    '🌐 NETWORK': ['pingurl', 'tcp', 'speed', 'speedtest', 'calc', 'calculate'],
    '⚡ SPAM': ['spam', 'dspam', 'cspam', 'dmspam', 'gcast', 'schedule', 'schedules'],
    '👋 WELCOME': ['setwelkm', 'resetwelkm', 'react', 'autoreact'],
    '🎮 GAMES': ['game', 'solver', 'wc', 'resetwords', 'grid', 'solvegrid', 'wordseek', 'gameinfo'],
    '💻 DEVELOPER': ['font', 'fonts', 'eval', 'sh', 'exec', 'plugins', 'update'],
}

commands = dict(DEFAULT_COMMANDS)
categories = dict(DEFAULT_CATEGORIES)
games = {}


# ─────────────────────────────────────────────────────────────────────────────
# Arqument parsinqi / argument parsing
# ─────────────────────────────────────────────────────────────────────────────
def _msg_text(message) -> str:
    if isinstance(message, str):
        return message
    return getattr(message, "raw_text", None) or getattr(message, "text", "") or ""


def get_arg(message) -> str:
    """Əmrdən sonrakı bütün mətn."""
    msg = _msg_text(message)
    if not msg:
        return ""
    if len(msg) > 1 and msg[0] in HARDCODED_PREFIXES and msg[1] == " ":
        msg = msg.replace(" ", "", 1)
    if msg and msg[0] in HARDCODED_PREFIXES:
        msg = msg[1:]
    split = msg.replace("\n", " \n").split(" ")
    rest = " ".join(split[1:]).strip()
    return rest


def get_args(message) -> List[str]:
    """Əmrdən sonrakı arqumentlər (shlex)."""
    text = _msg_text(message)
    if not text:
        return []
    parts = text.split(maxsplit=1)
    if len(parts) <= 1:
        return []
    rest = parts[1]
    try:
        split = shlex.split(rest)
    except ValueError:
        return rest.split()
    return [x for x in split if x]


def get_args_from_caret(message) -> List[str]:
    """Prefiksli əmrlərdən arqumentləri çıxar."""
    text = _msg_text(message)
    if not text or text[0] not in HARDCODED_PREFIXES:
        return []
    parts = text[1:].split()
    return parts[1:] if len(parts) > 1 else []


def get_command_from_caret(message) -> str:
    """Prefiksli əmrin adını qaytar."""
    text = _msg_text(message)
    if not text or text[0] not in HARDCODED_PREFIXES:
        return ""
    parts = text[1:].split()
    return parts[0] if parts else ""


def get_user(message, text):
    """Mətndən istifadəçi id/username və qalan mətni ayır."""
    if text:
        parts = text.split(maxsplit=1)
        first = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        if first.isdigit() or first.startswith("@"):
            return (int(first) if first.isdigit() else first), rest
    reply = getattr(message, "reply_to_msg_id", None)
    return None, text


async def extract_user(event, text=None):
    """Cavab və ya arqumentdən istifadəçini tap."""
    user, _ = await extract_user_and_reason(event, text)
    return user


async def extract_userid(event, text=None):
    user = await extract_user(event, text)
    return getattr(user, "id", None)


async def extract_user_and_reason(event, text=None):
    """(user_entity, reason) qaytarır."""
    client = event.client
    args = text if text is not None else get_arg(event)
    reply = await event.get_reply_message() if event.is_reply else None

    if reply:
        reason = args.strip() if args else ""
        try:
            user = await client.get_entity(reply.sender_id)
        except Exception:
            user = None
        return user, reason

    if not args:
        return None, ""

    parts = args.split(maxsplit=1)
    target = parts[0]
    reason = parts[1] if len(parts) > 1 else ""

    # mention entity
    for ent, val in (event.get_entities_text() or []):
        if isinstance(ent, types.MessageEntityMentionName):
            try:
                return await client.get_entity(ent.user_id), args.replace(val, "").strip()
            except Exception:
                pass

    try:
        if target.isdigit() or (target.startswith("-") and target[1:].isdigit()):
            user = await client.get_entity(int(target))
        else:
            user = await client.get_entity(target)
        return user, reason
    except Exception:
        return None, args


# ─────────────────────────────────────────────────────────────────────────────
# Zaman & qlobal dəyişənlər / time & gvars
# ─────────────────────────────────────────────────────────────────────────────
def get_readable_time(seconds: int) -> str:
    count = 0
    up_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]
    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)
    for x in range(len(time_list)):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        up_time += time_list.pop() + ", "
    time_list.reverse()
    up_time += ":".join(time_list)
    return up_time


class Timer:
    """Sadə throttle taymeri."""

    def __init__(self, timeout=3):
        self.timeout = timeout
        self.last = 0

    def can_send(self):
        now = time.time()
        if now - self.last >= self.timeout:
            self.last = now
            return True
        return False


def gvarstatus(name, user_id=None):
    """Qlobal dəyişəni oxu."""
    try:
        if user_id:
            data = cached_get_user_data(user_id)
            return data.get(name)
        doc = user_sessions.find_one({"gvar": name})
        return doc.get("value") if doc else None
    except Exception as exc:
        logger.warning(f"gvarstatus({name}) failed: {exc}")
        return None


def set_gvar(name, value, user_id=None):
    try:
        if user_id:
            user_sessions.update_one(
                {"user_id": user_id}, {"$set": {name: value}}, upsert=True
            )
            invalidate_session_cache(user_id)
        else:
            user_sessions.update_one(
                {"gvar": name}, {"$set": {"value": value}}, upsert=True
            )
        return True
    except Exception as exc:
        logger.warning(f"set_gvar({name}) failed: {exc}")
        return False


def unset_user_data(user_id, name):
    try:
        user_sessions.update_one({"user_id": user_id}, {"$unset": {name: ""}})
        invalidate_session_cache(user_id)
        return True
    except Exception as exc:
        logger.warning(f"unset_user_data({name}) failed: {exc}")
        return False


def get_user_data(user_id):
    return cached_get_user_data(user_id)


def format_welcome_message(template, user, chat_title=""):
    """Xoşgəldin şablonunu doldur."""
    mention = f"<a href='tg://user?id={getattr(user, 'id', 0)}'>{plain(getattr(user, 'first_name', 'User'))}</a>"
    return (
        (template or "")
        .replace("{mention}", mention)
        .replace("{first}", plain(getattr(user, "first_name", "") or ""))
        .replace("{last}", plain(getattr(user, "last_name", "") or ""))
        .replace("{username}", f"@{user.username}" if getattr(user, "username", None) else mention)
        .replace("{id}", str(getattr(user, "id", "")))
        .replace("{chat}", plain(chat_title))
    )


# ─────────────────────────────────────────────────────────────────────────────
# FloodWait / retry
# ─────────────────────────────────────────────────────────────────────────────
def retry(max_retries=3, initial_delay=5, backoff=2, exceptions=(FloodWaitError, OSError)):
    """Dekorator: FloodWait və müvəqqəti xətalarda təkrar cəhd edir."""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            retries = 0
            delay = initial_delay
            while retries < max_retries:
                try:
                    return await func(*args, **kwargs)
                except (MessageNotModifiedError, MessageIdInvalidError):
                    return None
                except exceptions as exc:
                    retries += 1
                    wait = getattr(exc, "seconds", None) or delay
                    logger.info(
                        f"Retry {retries}/{max_retries} for {func.__name__} after {wait}s"
                    )
                    await asyncio.sleep(wait)
                    delay *= backoff
                except Exception as exc:
                    logger.error(f"Unexpected error in {func.__name__}: {exc}")
                    raise
            return await func(*args, **kwargs)

        return wrapper

    return decorator


async def retry_call(coro_func, *args, attempts=3, delay=1, **kwargs):
    """İmperativ variant: `await retry_call(client.send_message, chat, text)`."""
    last_exc = None
    for i in range(attempts):
        try:
            return await coro_func(*args, **kwargs)
        except FloodWaitError as exc:
            wait = getattr(exc, "seconds", delay)
            logger.warning(f"FloodWait {wait}s — gözlənilir / waiting")
            await asyncio.sleep(wait + 1)
            last_exc = exc
        except (MessageNotModifiedError, MessageIdInvalidError):
            return None
        except Exception as exc:
            last_exc = exc
            await asyncio.sleep(delay * (i + 1))
    if last_exc:
        logger.warning(f"retry_call failed: {last_exc}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Fayl & media / files & media
# ─────────────────────────────────────────────────────────────────────────────
async def download_file(event, message=None, progress_msg=None):
    """Cavablanan medianı yüklə, yol qaytar."""
    target = message or (await event.get_reply_message() if event.is_reply else event)
    if not target or not target.media:
        return None
    return await target.download_media()


def rename_file(path, new_name):
    """Faylı yenidən adlandır və yeni yolu qaytar."""
    if not path or not os.path.exists(path):
        return path
    directory = os.path.dirname(path) or "."
    new_path = os.path.join(directory, new_name)
    try:
        os.rename(path, new_path)
        return new_path
    except Exception as exc:
        logger.warning(f"rename_file failed: {exc}")
        return path


def with_opencv(filename):
    """Videonun müddəti və kadr sayı."""
    if cv2 is None:
        return 0, 0
    try:
        video = cv2.VideoCapture(filename)
        fps = video.get(cv2.CAP_PROP_FPS) or 0
        frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = round(frame_count / fps) if fps else 0
        video.release()
        return duration, frame_count
    except Exception as exc:
        logger.warning(f"with_opencv failed: {exc}")
        return 0, 0


def generate_thumbnail(video_path, thumb_path="thumb.jpg"):
    """Videodan kiçik şəkil çıxar."""
    if cv2 is None:
        return None
    try:
        cap = cv2.VideoCapture(video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, 1)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None
        cv2.imwrite(thumb_path, frame)
        return thumb_path
    except Exception as exc:
        logger.warning(f"generate_thumbnail failed: {exc}")
        return None


async def run_cmd(cmd: str) -> Tuple[str, str, int, int]:
    """Shell əmrini işlət."""
    args = shlex.split(cmd)
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return (
        stdout.decode("utf-8", "replace").strip(),
        stderr.decode("utf-8", "replace").strip(),
        process.returncode,
        process.pid,
    )


async def convert_to_image(event, client=None) -> Optional[str]:
    """Hər cür medianı xam şəkilə çevir."""
    client = client or event.client
    reply = await event.get_reply_message() if event.is_reply else None
    if not reply or not reply.media:
        return None

    path = await reply.download_media()
    if not path:
        return None

    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg", ".png"):
        return path
    if ext == ".webp":
        final_path = "webp_to_png_ryhavean.png"
        Image.open(path).save(final_path, "PNG")
        return final_path
    if ext == ".tgs":
        final_path = "lottie_ryhavean.png"
        await run_cmd(f"lottie_convert.py --frame 0 -if lottie -of png {path} {final_path}")
        return final_path
    final_path = "fetched_thumb.png"
    await run_cmd(f"ffmpeg -i {path} -filter:v scale=500:500 -an {final_path}")
    return final_path if os.path.exists(final_path) else None


async def big_file(msg, sender, zip_filename):
    """2GB-dan böyük faylları gofile.io serverinə yüklə."""
    client = event_client = _get_bot_client() or _get_userbot_client()
    try:
        response = requests.get("https://api.gofile.io/servers", timeout=30)
        data = response.json()
        server = data["data"]["servers"][0]["name"]
    except Exception as exc:
        logger.error(f"gofile server lookup failed: {exc}")
        return await retry_call(bot.edit_message, msg, styled_error("gofile.io əlçatan deyil / unavailable"))

    await retry_call(bot.edit_message, msg, "📤 Fayl 2GB-dan böyükdür, gofile.io-ya yüklənir...")

    transfer_url = f"https://{server}.gofile.io/uploadFile"
    try:
        proc = subprocess.run(
            ["curl", "-F", f"file=@{zip_filename}", transfer_url],
            capture_output=True, text=True, timeout=3600,
        )
        text = proc.stdout or ""
        start_index = text.find("https://gofile.io")
        end_index = text.find('"', start_index)
        link = text[start_index:end_index] if start_index != -1 else None
        if link:
            await retry_call(client.send_message, sender, f"📎 Yükləmə linki / download link:\n{link}")
        else:
            await retry_call(bot.edit_message, msg, styled_error("Yükləmə uğursuz oldu / upload failed"))
    except Exception as exc:
        logger.error(f"gofile upload failed: {exc}")


def resize_image(image):
    im = Image.open(image)
    maxsize = (512, 512)
    if (im.width and im.height) < 512:
        size1 = im.width
        size2 = im.height
        if im.width > im.height:
            scale = 512 / size1
            size1new = 512
            size2new = size2 * scale
        else:
            scale = 512 / size2
            size1new = size1 * scale
            size2new = 512
        size1new = math.floor(size1new)
        size2new = math.floor(size2new)
        sizenew = (size1new, size2new)
        im = im.resize(sizenew)
    else:
        im.thumbnail(maxsize)
    file_name = "Sticker.png"
    im.save(file_name, "PNG")
    if os.path.exists(image):
        os.remove(image)
    return file_name


class Media_Info:
    def data(media: str) -> dict:
        "Get downloaded media's information"
        found = False
        media_info = MediaInfo.parse(media)
        for track in media_info.tracks:
            if track.track_type == "Video":
                found = True
                type_ = track.track_type
                format_ = track.format
                duration_1 = track.duration
                other_duration_ = track.other_duration
                duration_2 = (
                    f"{other_duration_[0]} - ({other_duration_[3]})"
                    if other_duration_
                    else None
                )
                pixel_ratio_ = [track.width, track.height]
                aspect_ratio_1 = track.display_aspect_ratio
                other_aspect_ratio_ = track.other_display_aspect_ratio
                aspect_ratio_2 = other_aspect_ratio_[0] if other_aspect_ratio_ else None
                fps_ = track.frame_rate
                fc_ = track.frame_count
                media_size_1 = track.stream_size
                other_media_size_ = track.other_stream_size
                media_size_2 = (
                    [
                        other_media_size_[1],
                        other_media_size_[2],
                        other_media_size_[3],
                        other_media_size_[4],
                    ]
                    if other_media_size_
                    else None
                )

        dict_ = (
            {
                "media_type": type_,
                "format": format_,
                "duration_in_ms": duration_1,
                "duration": duration_2,
                "pixel_sizes": pixel_ratio_,
                "aspect_ratio_in_fraction": aspect_ratio_1,
                "aspect_ratio": aspect_ratio_2,
                "frame_rate": fps_,
                "frame_count": fc_,
                "file_size_in_bytes": media_size_1,
                "file_size": media_size_2,
            }
            if found
            else None
        )
        return dict_


async def resize_media(media: str, video: bool, fast_forward: bool) -> str:
    if video:
        info_ = Media_Info.data(media)
        width = info_["pixel_sizes"][0]
        height = info_["pixel_sizes"][1]
        sec = info_["duration_in_ms"]
        s = round(float(sec)) / 1000

        if height == width:
            height, width = 512, 512
        elif height > width:
            height, width = 512, -1
        elif width > height:
            height, width = -1, 512

        resized_video = f"{media}.webm"
        if fast_forward:
            if s > 3:
                fract_ = 3 / s
                ff_f = round(fract_, 2)
                set_pts_ = ff_f - 0.01 if ff_f > fract_ else ff_f
                cmd_f = f"-filter:v 'setpts={set_pts_}*PTS',scale={width}:{height}"
            else:
                cmd_f = f"-filter:v scale={width}:{height}"
        else:
            cmd_f = f"-filter:v scale={width}:{height}"
        fps_ = float(info_["frame_rate"])
        fps_cmd = "-r 30 " if fps_ > 30 else ""
        cmd = f"ffmpeg -i {media} {cmd_f} -ss 00:00:00 -to 00:00:03 -an -c:v libvpx-vp9 {fps_cmd}-fs 256K {resized_video}"
        _, error, __, ___ = await run_cmd(cmd)
        os.remove(media)
        return resized_video

    image = Image.open(media)
    maxsize = 512
    scale = maxsize / max(image.width, image.height)
    new_size = (int(image.width * scale), int(image.height * scale))

    image = image.resize(new_size, Image.LANCZOS)
    resized_photo = "sticker.png"
    image.save(resized_photo)
    os.remove(media)
    return resized_photo

