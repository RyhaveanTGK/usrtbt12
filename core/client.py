"""
Ryhavean Userbot — Telethon klient qatı / client layer
──────────────────────────────────────────────────────
Userbot (istifadəçi hesabı) və köməkçi bot üçün TelegramClient yaradır.
Creates the Telethon clients for the userbot account and the helper bot.
"""

from __future__ import annotations

import logging
from typing import Optional

from telethon import TelegramClient
from telethon.sessions import StringSession

logger = logging.getLogger("core.client")


class RyhaveanClient(TelegramClient):
    """`.me` keşi olan TelegramClient (plaginlər `client.me.id` istifadə edir)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.me = None
        self.is_bot_client = False
        self.uid: Optional[int] = None

    async def refresh_me(self):
        self.me = await self.get_me()
        self.uid = self.me.id if self.me else None
        return self.me

    @property
    def username(self) -> Optional[str]:
        return getattr(self.me, "username", None)


def build_userbot(api_id: int, api_hash: str, session_string: str,
                  device_model: str = "Ryhavean Userbot") -> RyhaveanClient:
    client = RyhaveanClient(
        StringSession(session_string),
        api_id,
        api_hash,
        device_model=device_model,
        app_version="Ryhavean 2.0.0",
        system_version="Ryhavean OS",
        connection_retries=None,
        retry_delay=2,
        auto_reconnect=True,
        sequential_updates=False,
    )
    client.parse_mode = "html"
    return client


def build_bot(api_id: int, api_hash: str, bot_token: str,
              session_name: str = "ryhavean_bot") -> RyhaveanClient:
    client = RyhaveanClient(
        StringSession(),
        api_id,
        api_hash,
        device_model="Ryhavean Bot",
        app_version="Ryhavean 2.0.0",
        connection_retries=None,
        retry_delay=2,
        auto_reconnect=True,
    )
    client.parse_mode = "html"
    client.is_bot_client = True
    client._ryhavean_bot_token = bot_token
    return client
