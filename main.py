"""
Ryhavean Userbot — başlanğıc nöqtəsi / entry point (Telethon)
──────────────────────────────────────────────────────────────
Userbot + köməkçi bot, çoxdilli interfeys (AZ / TR / EN) və
premium emoji dəstəyi ilə birlikdə işə salınır.
"""

import asyncio
import logging
import os
import threading

from telethon import TelegramClient

import core.compat  # noqa: F401  (uyğunluq qatını qurur / installs compat layer)
import emoji_utils  # noqa: F401  (premium emoji yamalarını qurur)
import i18n
from config import *  # noqa: F401,F403
from core.client import build_bot, build_userbot
from core.dispatcher import attach_handlers
from plugin_loader import load_extra_plugins, load_plugin_file, load_package

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]",
)

logger = logging.getLogger("userbot")

BANNER = "═" * 50
print(BANNER)
print("🤖 RYHAVEAN USERBOT v2.0.0 — Telethon")
print(BANNER)
print("Başladılır... / Starting...")
print(BANNER)


async def main():
    # 1) Dil sistemi / language system
    i18n.install_hook()
    i18n.bind_storage(user_sessions)

    # 2) Sessiya / session
    session_string = SESSION_STR or input("Telethon sessiya sətrini daxil edin / Enter session string: ")

    # 3) Plaginləri idxal et — dekoratorlar registrə yazılır
    load_package("userbot")
    if BOT_TOKEN:
        load_package("bot")

    # 4) Köməkçi bot (opsional) / helper bot (optional)
    app = None
    if BOT_TOKEN:
        try:
            app = build_bot(API_ID, API_HASH, BOT_TOKEN)
            await app.start(bot_token=BOT_TOKEN)
            await app.refresh_me()
            attach_handlers(app, target="bot")
            apps["app"] = app
            print(f"✅ Bot işə düşdü / started: {app.me.first_name} (@{app.me.username})")
        except Exception as exc:
            print(f"⚠️ Bot başlamadı, davam edilir / bot failed, continuing: {exc}")
            app = None

    # 5) Userbot
    userbot = build_userbot(API_ID, API_HASH, session_string)
    try:
        await userbot.start()
        await userbot.refresh_me()
        attach_handlers(userbot, target="userbot")
        clients[userbot.uid] = userbot
        print(f"✅ Userbot işə düşdü / started: {userbot.me.first_name} (@{userbot.me.username})")
    except Exception as exc:
        print(f"❌ Userbot başlamadı / failed to start: {exc}")
        return

    # 6) Yadda saxlanılan dil / persisted language
    i18n.bind_storage(user_sessions, userbot.uid)
    active_lang = i18n.load_lang_from_db(userbot.uid)
    print(f"🌐 Aktiv dil / Active language: {active_lang}")

    # 7) Bazadan bərpa olunan istifadəçi plaginləri
    try:
        from userbot.plugin_installer import PLUGINS_DIR, restore_user_plugins

        restored = restore_user_plugins(userbot.uid)
        for name in restored:
            path = os.path.join(PLUGINS_DIR, str(userbot.uid), f"{name}.py")
            try:
                load_plugin_file(userbot, path, name)
                loaded_extra_plugins.append(name)
            except Exception as exc:
                logger.warning(f"Plagin '{name}' yüklənmədi / could not load: {exc}")
        if restored:
            print(f"📦 Bərpa olunan plaginlər / restored plugins: {', '.join(restored)}")
    except Exception as exc:
        logger.warning(f"Plaginlər bərpa olunmadı / plugin restore failed: {exc}")

    # 8) Sudo istifadəçiləri / sudo users
    user_data = user_sessions.find_one({"user_id": userbot.uid})
    if user_data and "sudoers" in user_data:
        SUDO[userbot.uid] = user_data["sudoers"]

    # 9) Xarici plaginlər / community plugins
    loaded_extra_plugins.extend(load_extra_plugins(userbot, EXTRA_PLUGINS_DIR))
    if loaded_extra_plugins:
        print(f"🧩 Əlavə plaginlər / extra plugins: {', '.join(loaded_extra_plugins)}")

    print(BANNER)
    print("🚀 Hazırdır / Ready — Ryhavean Userbot")
    print(BANNER)

    await userbot.run_until_disconnected()


def start_uptime_robot():
    """Render üçün HTTP sağlamlıq serveri."""
    try:
        import uptimerobot

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(uptimerobot.start_uptime_monitor())
    except Exception as exc:
        logger.warning(f"Uptime Robot server başlamadı / failed: {exc}")


if __name__ == "__main__":
    if os.getenv("DEPLOYMENT_PLATFORM") == "render" or os.getenv("RENDER"):
        logger.info("🌐 Render aşkarlandı / detected — uptime handler starting")
        threading.Thread(target=start_uptime_robot, daemon=True).start()

    logger.info("🚀 Ryhavean Userbot başladılır / is starting...")
    asyncio.run(main())
