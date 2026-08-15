"""
Ryhavean Userbot — Telethon dispatcher / handler registry
─────────────────────────────────────────────────────────
Bütün plaginlər əmrlərini bu modulun dekoratorları ilə qeyd edir.
All plugins register their commands through the decorators here.

İstifadə / Usage:

    from core.dispatcher import ryhavean_cmd, bot_cmd, on_event

    @ryhavean_cmd(["ping"], desc="Ping")
    async def ping(event):
        await event.edit("Pong!")

    @bot_cmd(["start"])
    async def start(event):
        await event.reply("Salam!")

Dekorator yalnız qeydiyyat aparır; həqiqi `add_event_handler` çağırışı
`attach_handlers(client, target)` funksiyasında baş verir (main.py).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from typing import Callable, Iterable, List, Optional

from telethon import events

logger = logging.getLogger("core.dispatcher")

# Userbot əmr prefiksləri / command prefixes
HARDCODED_PREFIXES = ["!", ".", "?", "^", "_"]

#: (target, callback, event_builder) üçlükləri
REGISTRY: List[tuple] = []

#: Qeyd olunmuş əmrlər — .help üçün
COMMAND_INDEX: dict = {}


def _prefix_class(prefixes: Iterable[str]) -> str:
    return "[" + "".join(re.escape(p) for p in prefixes) + "]"


def build_command_pattern(commands: Iterable[str], prefixes: Iterable[str]) -> re.Pattern:
    """`.cmd arqument` formasına uyğun regex qurur."""
    cmds = "|".join(re.escape(c) for c in sorted(commands, key=len, reverse=True))
    return re.compile(
        rf"^{_prefix_class(prefixes)}({cmds})(?:@[\w_]+)?(?:\s+([\s\S]*))?$",
        re.IGNORECASE,
    )


def register(callback: Callable, event_builder, target: str = "userbot") -> Callable:
    """Bir handler-i registrə əlavə et."""
    REGISTRY.append((target, callback, event_builder))
    existing = getattr(callback, "_ryhavean_handlers", [])
    existing.append((target, event_builder))
    callback._ryhavean_handlers = existing
    return callback


def _is_sudo(event) -> bool:
    """Göndərən sudo istifadəçisidirmi?"""
    try:
        from config import SUDO

        sender_id = event.sender_id
        if sender_id is None:
            return False
        for _owner, sudoers in SUDO.items():
            if sender_id in (sudoers or []):
                return True
    except Exception:
        return False
    return False


def _wrap(callback: Callable, *, sudo: bool, owner_only: bool,
          group_only: bool, private_only: bool, pattern: Optional[re.Pattern]):
    """Ortaq təhlükəsizlik/xəta qatı."""

    async def handler(event):
        try:
            from core.compat import enrich_event

            await enrich_event(event)

            if owner_only and not getattr(event, "out", False):
                if not (sudo and _is_sudo(event)):
                    return
            if group_only and not event.is_group:
                return
            if private_only and not event.is_private:
                return

            if pattern is not None:
                text = event.raw_text or ""
                match = pattern.match(text)
                if not match:
                    return
                event.ryhavean_command = match.group(1)
                event.ryhavean_args = (match.group(2) or "").strip()
                event.pattern_match = match
            else:
                if not hasattr(event, "ryhavean_args"):
                    event.ryhavean_args = ""

            await callback(event)
        except events.StopPropagation:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # heç bir plagin botu söndürməsin
            logger.exception("Handler xətası / handler error in %s: %s",
                             getattr(callback, "__name__", callback), exc)
            try:
                from core.errors import report_error

                await report_error(event, exc)
            except Exception:
                pass

    handler.__name__ = getattr(callback, "__name__", "handler")
    handler.__doc__ = callback.__doc__
    handler._ryhavean_original = callback
    return handler


def ryhavean_cmd(
    commands,
    *,
    prefixes: Optional[Iterable[str]] = None,
    sudo: bool = True,
    owner_only: bool = True,
    incoming: bool = False,
    outgoing: bool = True,
    group_only: bool = False,
    private_only: bool = False,
    edited: bool = True,
    desc: str = "",
    target: str = "userbot",
):
    """Userbot əmri qeyd edir (`.cmd` / `!cmd` / `?cmd` / `^cmd` / `_cmd`)."""
    if isinstance(commands, str):
        commands = [commands]
    commands = list(commands)
    prefixes = list(prefixes or HARDCODED_PREFIXES)
    pattern = build_command_pattern(commands, prefixes)

    def decorator(callback: Callable):
        wrapped = _wrap(
            callback,
            sudo=sudo,
            owner_only=owner_only,
            group_only=group_only,
            private_only=private_only,
            pattern=pattern,
        )
        builder = events.NewMessage(
            incoming=incoming or sudo,
            outgoing=outgoing,
        )
        register(wrapped, builder, target)
        if edited:
            register(wrapped, events.MessageEdited(incoming=incoming or sudo,
                                                   outgoing=outgoing), target)
        for cmd in commands:
            COMMAND_INDEX[cmd] = desc or (callback.__doc__ or "").strip()
        callback._ryhavean_wrapped = wrapped
        return callback

    return decorator


def bot_cmd(
    commands,
    *,
    prefixes: Iterable[str] = ("/", "!", "."),
    desc: str = "",
    private_only: bool = False,
):
    """Köməkçi bot əmri (`/cmd`)."""
    if isinstance(commands, str):
        commands = [commands]
    commands = list(commands)
    pattern = build_command_pattern(commands, prefixes)

    def decorator(callback: Callable):
        wrapped = _wrap(
            callback,
            sudo=False,
            owner_only=False,
            group_only=False,
            private_only=private_only,
            pattern=pattern,
        )
        register(wrapped, events.NewMessage(incoming=True), "bot")
        for cmd in commands:
            COMMAND_INDEX.setdefault(cmd, desc)
        callback._ryhavean_wrapped = wrapped
        return callback

    return decorator


def on_event(event_builder, target: str = "userbot"):
    """Xam Telethon hadisəsi (NewMessage, ChatAction, CallbackQuery, InlineQuery...)."""

    def decorator(callback: Callable):
        wrapped = _wrap(
            callback,
            sudo=False,
            owner_only=False,
            group_only=False,
            private_only=False,
            pattern=None,
        )
        register(wrapped, event_builder, target)
        callback._ryhavean_wrapped = wrapped
        return callback

    return decorator


def attach_handlers(client, target: str = "userbot") -> int:
    """Registrdəki bütün handlerləri Telethon klientinə bağla."""
    count = 0
    for tgt, callback, builder in REGISTRY:
        if tgt != target:
            continue
        client.add_event_handler(callback, builder)
        count += 1
    logger.info("[DISPATCHER] %s üçün %d handler bağlandı / attached", target, count)
    return count


def attach_module(client, module) -> int:
    """Bir modul içindəki handlerləri (runtime plagin) klientə bağla."""
    count = 0
    for attr in vars(module).values():
        handlers = getattr(attr, "_ryhavean_handlers", None)
        if not handlers:
            wrapped = getattr(attr, "_ryhavean_wrapped", None)
            handlers = getattr(wrapped, "_ryhavean_handlers", None) if wrapped else None
            attr = wrapped or attr
        if not handlers:
            continue
        for _target, builder in handlers:
            client.add_event_handler(attr, builder)
            count += 1
    return count


def is_coroutine_function(func) -> bool:
    return inspect.iscoroutinefunction(func)
