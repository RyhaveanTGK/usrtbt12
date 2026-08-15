"""Ryhavean Userbot — mərkəzi xəta bildirişi / central error reporting."""

from __future__ import annotations

import logging
import traceback

logger = logging.getLogger("core.errors")

#: Xətaları istifadəçiyə göstər (ENV: SHOW_ERRORS)
import os

SHOW_ERRORS = os.getenv("SHOW_ERRORS", "true").lower() in ("1", "true", "yes")


async def report_error(event, exc: Exception) -> None:
    """Xətanı loga yaz və (mümkünsə) istifadəçiyə qısa mesaj göstər."""
    logger.error("Xəta / error: %s\n%s", exc, traceback.format_exc())
    if not SHOW_ERRORS:
        return
    try:
        from i18n import translate

        text = translate(
            "❌ <b>Error</b>\n╰▸ <code>{}</code>".format(
                str(exc).replace("<", "&lt;").replace(">", "&gt;")[:300]
            )
        )
        if getattr(event, "out", False):
            await event.edit(text)
        else:
            await event.reply(text)
    except Exception:
        pass
