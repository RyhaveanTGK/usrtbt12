"""
Ryhavean Userbot — Telethon uyğunluq qatı / Telethon compatibility layer
────────────────────────────────────────────────────────────────────────
Plaginlər Telethon `event` obyektini alır, lakin köhnə tanış atributlar
(`message.chat.id`, `message.from_user`, `message.reply_to_message`,
`client.get_chat_history`, `client.send_photo` ...) da işləyir.

Bu qat yalnız *əlavə* edir — Telethon-un öz API-si tam əlçatandır.
"""

from __future__ import annotations

import logging
from typing import Optional

from telethon import TelegramClient, functions, types, utils
from telethon.errors import UserNotParticipantError
from telethon.tl.custom import Message
from telethon.tl.functions.channels import EditAdminRequest, EditBannedRequest
from telethon.tl.types import ChatAdminRights, ChatBannedRights

logger = logging.getLogger("core.compat")

# ─────────────────────────────────────────────────────────────────────────────
# Sabitlər / constants
# ─────────────────────────────────────────────────────────────────────────────
BAN_RIGHTS = ChatBannedRights(until_date=None, view_messages=True)
UNBAN_RIGHTS = ChatBannedRights(
    until_date=None,
    view_messages=False,
    send_messages=False,
    send_media=False,
    send_stickers=False,
    send_gifs=False,
    send_games=False,
    send_inline=False,
    embed_links=False,
)
MUTE_RIGHTS = ChatBannedRights(until_date=None, send_messages=True)
UNMUTE_RIGHTS = ChatBannedRights(until_date=None, send_messages=False)
KICK_RIGHTS = ChatBannedRights(until_date=None, view_messages=True)


# ─────────────────────────────────────────────────────────────────────────────
# Message əlavələri / message additions
# ─────────────────────────────────────────────────────────────────────────────
def _install_message_helpers():
    if getattr(Message, "_ryhavean_compat", False):
        return

    async def download(self, *args, **kwargs):
        """Pyrogram-uyğun `message.download()`."""
        return await self.download_media(*args, **kwargs)

    async def reply_text(self, text, **kwargs):
        return await self.reply(text, **kwargs)

    async def edit_text(self, text, **kwargs):
        return await self.edit(text, **kwargs)

    @property
    def message_id(self):
        return self.id

    @property
    def caption(self):
        return self.text if self.media else None

    @property
    def outgoing(self):
        return bool(self.out)

    @property
    def command(self):
        """`['cmd', 'arg1', 'arg2']` — Pyrogram `message.command` bənzəri."""
        text = self.raw_text or ""
        if not text:
            return []
        parts = text.split()
        if not parts:
            return []
        head = parts[0]
        if head and not head[0].isalnum():
            head = head[1:]
        return [head] + parts[1:]

    Message.download = download
    Message.reply_text = reply_text
    Message.edit_text = edit_text
    Message.message_id = message_id
    Message.outgoing = outgoing
    Message.command = command
    if not hasattr(Message, "caption"):
        Message.caption = caption
    Message._ryhavean_compat = True


# ─────────────────────────────────────────────────────────────────────────────
# Client əlavələri / client additions
# ─────────────────────────────────────────────────────────────────────────────
def _install_client_helpers():
    if getattr(TelegramClient, "_ryhavean_compat", False):
        return

    def get_chat_history(self, chat_id, limit=100, **kwargs):
        """Telethon `iter_messages` üzərində Pyrogram adı."""
        return self.iter_messages(chat_id, limit=limit, **kwargs)

    def search_messages(self, chat_id, query="", from_user=None, limit=None, **kwargs):
        return self.iter_messages(
            chat_id, search=query or None, from_user=from_user, limit=limit, **kwargs
        )

    async def get_chat(self, chat_id):
        return await self.get_entity(chat_id)

    async def get_users(self, user_ids):
        return await self.get_entity(user_ids)

    async def resolve_peer(self, peer):
        return await self.get_input_entity(peer)

    async def send_photo(self, chat_id, photo, caption=None, **kwargs):
        return await self.send_file(chat_id, photo, caption=caption, **kwargs)

    async def send_video(self, chat_id, video, caption=None, **kwargs):
        return await self.send_file(
            chat_id, video, caption=caption, supports_streaming=True, **kwargs
        )

    async def send_audio(self, chat_id, audio, caption=None, **kwargs):
        return await self.send_file(chat_id, audio, caption=caption, **kwargs)

    async def send_document(self, chat_id, document, caption=None, **kwargs):
        return await self.send_file(
            chat_id, document, caption=caption, force_document=True, **kwargs
        )

    async def send_animation(self, chat_id, animation, caption=None, **kwargs):
        return await self.send_file(chat_id, animation, caption=caption, **kwargs)

    async def send_sticker(self, chat_id, sticker, **kwargs):
        return await self.send_file(chat_id, sticker, **kwargs)

    async def send_voice(self, chat_id, voice, **kwargs):
        return await self.send_file(chat_id, voice, voice_note=True, **kwargs)

    async def edit_message_text(self, chat_id, message_id, text, **kwargs):
        return await self.edit_message(chat_id, message_id, text, **kwargs)

    async def ban_chat_member(self, chat_id, user_id, **kwargs):
        return await self(EditBannedRequest(chat_id, user_id, BAN_RIGHTS))

    async def unban_chat_member(self, chat_id, user_id, **kwargs):
        return await self(EditBannedRequest(chat_id, user_id, UNBAN_RIGHTS))

    async def restrict_chat_member(self, chat_id, user_id, rights=None, **kwargs):
        return await self(
            EditBannedRequest(chat_id, user_id, rights or MUTE_RIGHTS)
        )

    async def promote_chat_member(self, chat_id, user_id, rights=None, rank="", **kwargs):
        admin_rights = rights or ChatAdminRights(
            change_info=True,
            post_messages=True,
            edit_messages=True,
            delete_messages=True,
            ban_users=True,
            invite_users=True,
            pin_messages=True,
            add_admins=False,
            manage_call=True,
        )
        return await self(EditAdminRequest(chat_id, user_id, admin_rights, rank))

    async def get_chat_member(self, chat_id, user_id):
        try:
            return await self.get_permissions(chat_id, user_id)
        except UserNotParticipantError:
            return None

    TelegramClient.get_chat_history = get_chat_history
    TelegramClient.search_messages = search_messages
    TelegramClient.get_chat = get_chat
    TelegramClient.get_users = get_users
    TelegramClient.resolve_peer = resolve_peer
    TelegramClient.send_photo = send_photo
    TelegramClient.send_video = send_video
    TelegramClient.send_audio = send_audio
    TelegramClient.send_document = send_document
    TelegramClient.send_animation = send_animation
    TelegramClient.send_sticker = send_sticker
    TelegramClient.send_voice = send_voice
    TelegramClient.edit_message_text = edit_message_text
    TelegramClient.ban_chat_member = ban_chat_member
    TelegramClient.unban_chat_member = unban_chat_member
    TelegramClient.restrict_chat_member = restrict_chat_member
    TelegramClient.promote_chat_member = promote_chat_member
    TelegramClient.get_chat_member = get_chat_member
    TelegramClient._ryhavean_compat = True


async def enrich_event(event) -> None:
    """Handler-dən əvvəl tanış atributları hazırla (await tələb edənlər)."""
    if getattr(event, "_ryhavean_enriched", False):
        return
    try:
        event.from_user = await event.get_sender()
    except Exception:
        event.from_user = None
    try:
        await event.get_chat()  # `event.chat` keşə yazılır
    except Exception:
        pass
    try:
        event.reply_to_message = (
            await event.get_reply_message() if event.is_reply else None
        )
    except Exception:
        event.reply_to_message = None
    event._ryhavean_enriched = True


def install() -> None:
    """Uyğunluq qatını qur (main.py bir dəfə çağırır)."""
    _install_message_helpers()
    _install_client_helpers()
    logger.info("[COMPAT] Telethon uyğunluq qatı quruldu / installed")


install()


# ─────────────────────────────────────────────────────────────────────────────
# Klaviatura uyğunluğu / keyboard compatibility
# ─────────────────────────────────────────────────────────────────────────────
from telethon import Button  # noqa: E402


def InlineKeyboardButton(text, callback_data=None, url=None, switch_inline_query=None,
                         switch_inline_query_current_chat=None, **kwargs):
    """Pyrogram adı ilə Telethon `Button` yaradır."""
    if url:
        return Button.url(text, url)
    if switch_inline_query is not None:
        return Button.switch_inline(text, switch_inline_query, same_peer=False)
    if switch_inline_query_current_chat is not None:
        return Button.switch_inline(text, switch_inline_query_current_chat, same_peer=True)
    data = callback_data if callback_data is not None else text
    if isinstance(data, str):
        data = data.encode()
    return Button.inline(text, data)


def InlineKeyboardMarkup(inline_keyboard):
    """Sətir siyahısını olduğu kimi qaytarır (Telethon `buttons=` gözləyir)."""
    return list(inline_keyboard)


def ReplyKeyboardMarkup(keyboard, **kwargs):
    return [[Button.text(b) if isinstance(b, str) else b for b in row] for row in keyboard]


class KeyboardButton(str):
    """Sadə mətn düyməsi."""

    def __new__(cls, text, **kwargs):
        return super().__new__(cls, text)


# ─────────────────────────────────────────────────────────────────────────────
# Enum uyğunluğu / enum compatibility
# ─────────────────────────────────────────────────────────────────────────────
class ChatMemberStatus:
    OWNER = "creator"
    ADMINISTRATOR = "administrator"
    MEMBER = "member"
    RESTRICTED = "restricted"
    LEFT = "left"
    BANNED = "banned"


class ChatType:
    PRIVATE = "private"
    BOT = "bot"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"


class UserStatus:
    ONLINE = "online"
    OFFLINE = "offline"
    RECENTLY = "recently"
    LAST_WEEK = "last_week"
    LAST_MONTH = "last_month"
    LONG_AGO = "long_ago"


class MessageEntityType:
    TEXT_MENTION = "text_mention"
    MENTION = "mention"
    ITALIC = "italic"
    BOLD = "bold"
    CODE = "code"
    PRE = "pre"
    URL = "url"
    TEXT_LINK = "text_link"
    CUSTOM_EMOJI = "custom_emoji"


class ChatAction:
    TYPING = "typing"
    UPLOAD_PHOTO = "photo"
    UPLOAD_VIDEO = "video"
    UPLOAD_DOCUMENT = "document"
    RECORD_AUDIO = "record-audio"
    CHOOSE_STICKER = "sticker"
    CANCEL = "cancel"


class ChatMembersFilter:
    SEARCH = "search"
    ADMINISTRATORS = "administrators"
    BANNED = "banned"
    RESTRICTED = "restricted"
    BOTS = "bots"
    RECENT = "recent"


class ParseMode:
    HTML = "html"
    MARKDOWN = "md"
    DISABLED = None


class _Enums:
    ChatMemberStatus = ChatMemberStatus
    ChatType = ChatType
    UserStatus = UserStatus
    MessageEntityType = MessageEntityType
    ChatAction = ChatAction
    ChatMembersFilter = ChatMembersFilter
    ParseMode = ParseMode


enums = _Enums()


def entity_type_name(entity) -> str:
    """Telethon entity obyektinin Pyrogram-vari adı."""
    name = type(entity).__name__.replace("MessageEntity", "")
    mapping = {
        "MentionName": MessageEntityType.TEXT_MENTION,
        "Mention": MessageEntityType.MENTION,
        "Italic": MessageEntityType.ITALIC,
        "Bold": MessageEntityType.BOLD,
        "Code": MessageEntityType.CODE,
        "Pre": MessageEntityType.PRE,
        "Url": MessageEntityType.URL,
        "TextUrl": MessageEntityType.TEXT_LINK,
        "CustomEmoji": MessageEntityType.CUSTOM_EMOJI,
    }
    return mapping.get(name, name.lower())


def user_status_name(status) -> str:
    """Telethon UserStatus* -> mətn."""
    name = type(status).__name__.replace("UserStatus", "")
    mapping = {
        "Online": UserStatus.ONLINE,
        "Offline": UserStatus.OFFLINE,
        "Recently": UserStatus.RECENTLY,
        "LastWeek": UserStatus.LAST_WEEK,
        "LastMonth": UserStatus.LAST_MONTH,
        "Empty": UserStatus.LONG_AGO,
    }
    return mapping.get(name, UserStatus.LONG_AGO)


def _install_extra_client_helpers():
    from telethon.tl.types import (
        ChannelParticipantsAdmins,
        ChannelParticipantsBanned,
        ChannelParticipantsBots,
        ChannelParticipantsKicked,
        ChannelParticipantsRecent,
        ChannelParticipantsSearch,
    )

    _FILTERS = {
        ChatMembersFilter.ADMINISTRATORS: lambda q: ChannelParticipantsAdmins(),
        ChatMembersFilter.BANNED: lambda q: ChannelParticipantsKicked(q or ""),
        ChatMembersFilter.RESTRICTED: lambda q: ChannelParticipantsBanned(q or ""),
        ChatMembersFilter.BOTS: lambda q: ChannelParticipantsBots(),
        ChatMembersFilter.RECENT: lambda q: ChannelParticipantsRecent(),
        ChatMembersFilter.SEARCH: lambda q: ChannelParticipantsSearch(q or ""),
    }

    def get_chat_members(self, chat_id, query="", filter=None, limit=None, **kwargs):
        flt = _FILTERS.get(filter)
        return self.iter_participants(
            chat_id,
            search=query or None,
            filter=flt(query) if flt else None,
            limit=limit,
        )

    async def send_chat_action(self, chat_id, action="typing", **kwargs):
        async with self.action(chat_id, action or "typing"):
            return True

    TelegramClient.get_chat_members = get_chat_members
    TelegramClient.send_chat_action = send_chat_action


_install_extra_client_helpers()


def _install_permission_status():
    """`member.status` və `member.privileges` Pyrogram adları."""
    try:
        from telethon.tl.custom.participantpermissions import ParticipantPermissions
    except Exception:  # pragma: no cover
        return

    if getattr(ParticipantPermissions, "_ryhavean_compat", False):
        return

    @property
    def status(self):
        if self.is_creator:
            return ChatMemberStatus.OWNER
        if self.is_admin:
            return ChatMemberStatus.ADMINISTRATOR
        if self.is_banned:
            return ChatMemberStatus.BANNED
        if getattr(self, "has_left", False):
            return ChatMemberStatus.LEFT
        return ChatMemberStatus.MEMBER

    @property
    def privileges(self):
        return self

    @property
    def can_restrict_members(self):
        return bool(self.ban_users)

    @property
    def can_promote_members(self):
        return bool(self.add_admins)

    @property
    def can_delete_messages(self):
        return bool(self.delete_messages)

    @property
    def can_pin_messages(self):
        return bool(self.pin_messages)

    @property
    def can_invite_users(self):
        return bool(self.invite_users)

    @property
    def can_change_info(self):
        return bool(self.change_info)

    @property
    def can_manage_video_chats(self):
        return bool(getattr(self, "manage_call", False))

    ParticipantPermissions.status = status
    ParticipantPermissions.privileges = privileges
    for name, prop in (
        ("can_restrict_members", can_restrict_members),
        ("can_promote_members", can_promote_members),
        ("can_delete_messages", can_delete_messages),
        ("can_pin_messages", can_pin_messages),
        ("can_invite_users", can_invite_users),
        ("can_change_info", can_change_info),
        ("can_manage_video_chats", can_manage_video_chats),
    ):
        if not hasattr(ParticipantPermissions, name):
            setattr(ParticipantPermissions, name, prop)
    ParticipantPermissions._ryhavean_compat = True


_install_permission_status()


# ─────────────────────────────────────────────────────────────────────────────
# Söhbət gözləyicisi / conversation listener (convopyro əvəzi)
# ─────────────────────────────────────────────────────────────────────────────
import asyncio as _asyncio  # noqa: E402
import re as _re  # noqa: E402

from telethon import events as _events  # noqa: E402


class _Listener:
    """`await client.listen.Message(chat=..., func=..., timeout=10)`."""

    def __init__(self, client):
        self._client = client

    async def Message(self, chat=None, from_user=None, pattern=None, func=None,
                      timeout=10, incoming=True):
        loop = _asyncio.get_event_loop()
        future = loop.create_future()
        compiled = _re.compile(pattern) if isinstance(pattern, str) else pattern

        async def _handler(event):
            if future.done():
                return
            try:
                if from_user is not None and event.sender_id != from_user:
                    return
                if compiled is not None and not compiled.search(event.raw_text or ""):
                    return
                if func is not None:
                    result = func(event)
                    if _asyncio.iscoroutine(result):
                        result = await result
                    if not result:
                        return
                await enrich_event(event)
                future.set_result(event)
            except Exception:
                pass

        builder = _events.NewMessage(chats=chat, incoming=incoming)
        self._client.add_event_handler(_handler, builder)
        try:
            return await _asyncio.wait_for(future, timeout=timeout)
        except _asyncio.TimeoutError:
            return None
        finally:
            self._client.remove_event_handler(_handler, builder)

    async def ask(self, chat, text, timeout=30, **kwargs):
        """Sual göndər və cavabı gözlə."""
        sent = await self._client.send_message(chat, text, **kwargs)
        answer = await self.Message(chat=chat, timeout=timeout)
        if answer is not None:
            answer.request = sent
        return answer


def _listen_property(self):
    listener = getattr(self, "_ryhavean_listener", None)
    if listener is None:
        listener = _Listener(self)
        self._ryhavean_listener = listener
    return listener


TelegramClient.listen = property(_listen_property)


async def _client_ask(self, chat, text, timeout=30, **kwargs):
    return await self.listen.ask(chat, text, timeout=timeout, **kwargs)


TelegramClient.ask = _client_ask
