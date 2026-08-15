from collections import OrderedDict
from config import *
from tools import *

# ponytail: bounded in-memory cache. Telegram's delete update for private chats
# carries only message IDs (no chat, no content), so we must remember incoming
# messages ourselves to log what was deleted/edited. Private msg IDs are unique
# per account, so keying by message.id alone is safe.
# Cap at 2000; oldest evicted. Lost on restart — fine, this is a convenience log.
_CACHE = OrderedDict()
_CACHE_MAX = 2000

_MEDIA_ATTRS = ("photo", "video", "audio", "voice", "video_note", "animation", "document", "sticker")


def _media_of(message):
    for attr in _MEDIA_ATTRS:
        obj = getattr(message, attr, None)
        if obj:
            return attr, getattr(obj, "id", None)
    return None, None


def _remember(message):
    m_type, file_id = _media_of(message)
    _CACHE[message.id] = {
        "text": message.text or message.caption or "",
        "media_type": m_type,
        "file_id": file_id,
        "user": message.from_user,
    }
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


def _who(user):
    if not user:
        return "unknown"
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    uname = f" (@{user.username})" if user.username else ""
    return f"[{name}](tg://user?id={user.id}){uname} `{user.id}`"


# group=2: overlaps antyspam (group 0) and auto_download (group 1) on private
# non-me non-bot messages; separate group so all three run independently.
@on_event(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def _cache_incoming(event):
    client = event.client
    message = event
    _remember(message)


@on_event(events.MessageEdited(incoming=True, func=lambda e: e.is_private))
async def _log_edited(event):
    client = event.client
    message = event
    cached = _CACHE.get(message.id)
    old = cached["text"] if cached else "_(not cached)_"
    new = message.text or message.caption or ""
    if old == new:
        return
    _remember(message)  # keep cache current for a later delete
    text = (
        f"✏️ **Edited message** in PM\n"
        f"👤 {_who(message.from_user)}\n\n"
        f"**Before:**\n{old}\n\n"
        f"**After:**\n{new}"
    )
    try:
        await client.send_message(client.uid, text, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"[LOGGER] edited-log failed: {e}")


# No filter: private-chat delete updates have message.chat == None, so
# filters.private would never match. We only act on IDs we cached (which are
# private-only by construction), so this is implicitly scoped correctly.
@on_event(events.MessageDeleted())
async def _log_deleted(event):
    client = event.client
    messages = event
    for message in messages:
        cached = _CACHE.pop(message.id, None)
        if not cached:
            continue
        text = (
            f"🗑 **Deleted message** in PM\n"
            f"👤 {_who(cached['user'])}\n\n"
            f"{cached['text'] or '_(no text)_'}"
        )
        try:
            await client.send_message(client.uid, text, disable_web_page_preview=True)
            if cached["file_id"]:
                send = getattr(client, f"send_{cached['media_type']}", None)
                if send:
                    await send(client.uid, cached["file_id"])
        except Exception as e:
            logger.error(f"[LOGGER] deleted-log failed: {e}")
