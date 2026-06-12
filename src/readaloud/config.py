from __future__ import annotations

import os
import tempfile
import tomllib
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from .paths import config_path

MIN_LENGTH_SCALE = 0.35
MAX_LENGTH_SCALE = 4.0


@dataclass(frozen=True)
class Config:
    voice: str = "en_US-lessac-high"
    rate: int = 50
    sentence_silence: float = 0.05
    volume: float = 1.0
    audio_backend: str = "auto"

    @property
    def length_scale(self) -> float:
        denominator = 1 + self.rate / 100
        if denominator <= 0:
            return MAX_LENGTH_SCALE
        raw = 0.8 / denominator
        return min(MAX_LENGTH_SCALE, max(MIN_LENGTH_SCALE, raw))


FIELDS = {
    "voice": str,
    "rate": int,
    "sentence_silence": (int, float),
    "volume": (int, float),
    "audio_backend": str,
}


def validate(config: Config) -> Config:
    if not config.voice or "/" in config.voice or config.voice in {".", ".."}:
        raise ValueError("voice must be a simple non-empty name")
    if isinstance(config.rate, bool) or not -100 <= config.rate <= 100:
        raise ValueError("rate must be an integer from -100 to 100")
    if not 0 <= config.sentence_silence <= 2:
        raise ValueError("sentence_silence must be from 0 to 2 seconds")
    if not 0 <= config.volume <= 2:
        raise ValueError("volume must be from 0 to 2")
    if config.audio_backend not in {"auto", "pipewire", "pulse"}:
        raise ValueError("audio_backend must be auto, pipewire, or pulse")
    return config


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        return Config()
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    unknown = set(raw) - set(FIELDS)
    if unknown:
        raise ValueError(f"unknown configuration keys: {', '.join(sorted(unknown))}")
    for key, value in raw.items():
        expected = FIELDS[key]
        if isinstance(value, bool) or not isinstance(value, expected):
            raise ValueError(f"invalid type for {key}")
    return validate(Config(**raw))


def _toml(config: Config) -> str:
    values = asdict(config)
    lines = []
    for key in FIELDS:
        value = values[key]
        if isinstance(value, str):
            value = '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        elif isinstance(value, float):
            value = repr(value)
        lines.append(f"{key} = {value}")
    return "\n".join(lines) + "\n"


def save(config: Config, path: Path | None = None) -> None:
    config = validate(config)
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".config.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(_toml(config))
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def set_value(config: Config, key: str, raw: str) -> Config:
    if key not in FIELDS:
        raise ValueError(f"unknown configuration key: {key}")
    if key == "rate":
        value: Any = int(raw)
    elif key in {"sentence_silence", "volume"}:
        value = float(raw)
    else:
        value = raw
    return validate(replace(config, **{key: value}))
