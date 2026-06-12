from __future__ import annotations

import os
from pathlib import Path


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))


def runtime_dir() -> Path:
    value = os.environ.get("XDG_RUNTIME_DIR")
    if not value:
        raise RuntimeError("XDG_RUNTIME_DIR is not set")
    return Path(value) / "readaloud"


def config_path() -> Path:
    return config_home() / "readaloud" / "config.toml"


def voices_dir() -> Path:
    return data_home() / "readaloud" / "voices"


def socket_path() -> Path:
    return runtime_dir() / "control.sock"
