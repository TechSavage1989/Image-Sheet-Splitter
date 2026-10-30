import json
import os
import shutil
from pathlib import Path

APP_DIR_NAME = "ImageSheetSplitter"
LEGACY_DIR_NAME = "SpriteSheetSplitter"
CONFIG_FILE_NAME = "Image_Sheet_Splitter.config.json"
LEGACY_CONFIG_FILE_NAME = "Sprite_Sheet_Splitter.config.json"
CONFIG_LOCATOR_NAME = "config_location.txt"


def _local_appdata_root():
    if os.name == "nt":
        value = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if value:
            return Path(value)
    return Path.home() / ".local" / "share"


def user_data_root():
    return _local_appdata_root() / APP_DIR_NAME


def legacy_user_data_root():
    return _local_appdata_root() / LEGACY_DIR_NAME


def config_locator_path():
    return user_data_root() / CONFIG_LOCATOR_NAME


def legacy_config_locator_path():
    return legacy_user_data_root() / CONFIG_LOCATOR_NAME


def default_config_path():
    return user_data_root() / CONFIG_FILE_NAME


def legacy_default_config_path():
    return legacy_user_data_root() / LEGACY_CONFIG_FILE_NAME


def logs_dir():
    return user_data_root() / "Logs"


def cache_dir():
    return user_data_root() / "Cache"


def downloads_dir():
    return user_data_root() / "Downloads"


def staging_dir():
    return user_data_root() / "Staging"


def rollback_dir():
    return user_data_root() / "Rollback"


def update_state_path():
    return cache_dir() / "update-state.json"


def _read_locator(path):
    try:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return Path(value).expanduser()
    except OSError:
        pass
    return None


def _write_locator(path):
    try:
        locator = config_locator_path()
        locator.parent.mkdir(parents=True, exist_ok=True)
        locator.write_text(str(path), encoding="utf-8")
    except OSError:
        pass


def resolve_config_path():
    current = _read_locator(config_locator_path())
    if current:
        return current

    legacy_custom = _read_locator(legacy_config_locator_path())
    if legacy_custom:
        _write_locator(legacy_custom)
        return legacy_custom

    current_default = default_config_path()
    if current_default.exists():
        return current_default

    legacy_default = legacy_default_config_path()
    if legacy_default.exists():
        try:
            current_default.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(legacy_default, current_default)
            _write_locator(current_default)
            return current_default
        except OSError:
            return legacy_default

    return current_default


def default_settings():
    root = user_data_root()
    return {
        "output_dir": "",
        "open_export_folder": True,
        "tolerance": 8,
        "min_width": 8,
        "min_height": 8,
        "logging_enabled": True,
        "log_dir": str(root / "Logs"),
    }


def load_settings(path):
    settings = default_settings()
    try:
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                for key in settings:
                    if key in loaded:
                        settings[key] = loaded[key]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return settings

    legacy_log_default = legacy_user_data_root() / "Logs"
    try:
        configured = Path(str(settings.get("log_dir", ""))).expanduser()
        if configured == legacy_log_default:
            settings["log_dir"] = str(logs_dir())
    except (TypeError, ValueError):
        pass
    return settings


def write_config_locator(path):
    _write_locator(path)


def ensure_runtime_dirs():
    for folder in (user_data_root(), cache_dir(), downloads_dir(), staging_dir(), rollback_dir()):
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
