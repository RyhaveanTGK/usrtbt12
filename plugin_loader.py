"""
Ryhavean Userbot — plagin yükləyici / plugin loader (Telethon)
───────────────────────────────────────────────────────────────
Plaginlər `@ryhavean_cmd` / `@bot_cmd` / `@on_event` dekoratorları ilə
`core.dispatcher.REGISTRY`-yə yazılır. Bu modul:

  • `load_package("userbot")` — paketdəki bütün faylları idxal edir
    (dekoratorlar registrə düşür, `attach_handlers` sonra bağlayır);
  • `load_plugin_file(client, path)` — tək faylı idxal edib handlerlərini
    dərhal klientə bağlayır (restart tələb olunmur);
  • `load_extra_plugins(client, dir)` — icma plaginləri qovluğu.

Hər fayl təcrid olunmuş şəkildə yüklənir: bir plagindəki xəta loglanır və
ötürülür, heç vaxt başlanğıcı dayandırmır.
"""

import importlib
import importlib.util
import logging
import pkgutil
from pathlib import Path

from core.dispatcher import attach_module

logger = logging.getLogger("plugins")


def load_package(package_name: str):
    """Paketdəki bütün plagin modullarını idxal et."""
    loaded = []
    try:
        package = importlib.import_module(package_name)
    except Exception as exc:
        logger.error("[PLUGINS] '%s' paketi idxal olunmadı / import failed: %s", package_name, exc)
        return loaded

    for _finder, name, _ispkg in pkgutil.iter_modules(package.__path__):
        if name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{package_name}.{name}")
            loaded.append(name)
        except Exception as exc:
            logger.warning("[PLUGINS] %s.%s yüklənmədi / failed: %s", package_name, name, exc)

    logger.info("[PLUGINS] '%s' paketindən %d modul / modules loaded", package_name, len(loaded))
    return loaded


def load_plugin_file(client, path, name=None):
    """Tək `.py` plaginini idxal et və handlerlərini dərhal qeyd et."""
    path = Path(path)
    stem = name or path.stem
    spec = importlib.util.spec_from_file_location(f"user_plugins.{stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    count = attach_module(client, module)
    logger.info("[PLUGINS] %s faylından %d handler / handlers from %s", path.name, count, path.name)
    return count


def load_extra_plugins(client, directory):
    """Qovluqdakı bütün `*.py` plaginlərini yüklə."""
    loaded = []
    d = Path(directory)
    if not d.is_dir():
        logger.info("[PLUGINS] Əlavə plagin qovluğu yoxdur / no extra dir at %s", directory)
        return loaded

    for path in sorted(d.rglob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            count = load_plugin_file(client, path)
        except Exception as exc:
            logger.warning("[PLUGINS] %s idxal olunmadı / import failed: %s", path.name, exc)
            continue
        if count:
            loaded.append(path.stem)
        else:
            logger.warning("[PLUGINS] %s içində handler tapılmadı / no handlers", path.name)

    return loaded
