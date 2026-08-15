import logging


from tools import *
from config import EXTRA_PLUGINS_DIR, loaded_extra_plugins

logger = logging.getLogger("userbot.plugins")


@ryhavean_cmd("plugins", sudo=True)
async def plugins_handler(event):
    client = event.client
    message = event
    """Lists community plugins loaded from EXTRA_PLUGINS_DIR."""
    if loaded_extra_plugins:
        listing = "\n".join(f"┃ • `{name}`" for name in loaded_extra_plugins)
        text = (
            f"🧩 **Loaded plugins** ({len(loaded_extra_plugins)})\n"
            f"┃ 📂 `{EXTRA_PLUGINS_DIR}`\n"
            f"{listing}\n"
            f"╰━━━━━━━━━━━━━━━━━━━━╯"
        )
    else:
        text = (
            f"🧩 **No external plugins loaded**\n"
            f"┃ 📂 Drop `.py` files in `{EXTRA_PLUGINS_DIR}` and restart.\n"
            f"╰━━━━━━━━━━━━━━━━━━━━╯"
        )
    await edit_or_reply(message, text)
