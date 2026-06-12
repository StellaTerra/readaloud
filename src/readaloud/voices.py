from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import voices_dir


@dataclass(frozen=True)
class VoiceEntry:
    name: str
    model_url: str
    model_sha256: str
    config_url: str
    config_sha256: str
    model_card_url: str
    license: str


def load_catalog(path: Path) -> dict[str, VoiceEntry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {item["name"]: VoiceEntry(**item) for item in raw["voices"]}


def model_path(name: str, directory: Path | None = None) -> Path:
    return (directory or voices_dir()) / name / f"{name}.onnx"


def installed(name: str, directory: Path | None = None) -> bool:
    model = model_path(name, directory)
    return model.is_file() and model.with_suffix(".onnx.json").is_file()


def _download(url: str, destination: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with urllib.request.urlopen(url) as source, destination.open("wb") as target:
        while block := source.read(1024 * 1024):
            digest.update(block)
            target.write(block)
    actual = digest.hexdigest()
    if actual != expected:
        raise RuntimeError(f"checksum mismatch for {url}: expected {expected}, got {actual}")


def install(entry: VoiceEntry, directory: Path | None = None) -> Path:
    root = directory or voices_dir()
    root.mkdir(parents=True, exist_ok=True)
    target = root / entry.name
    if installed(entry.name, root):
        return target
    temporary = Path(tempfile.mkdtemp(prefix=f".{entry.name}.", dir=root))
    try:
        model = temporary / f"{entry.name}.onnx"
        _download(entry.model_url, model, entry.model_sha256)
        _download(entry.config_url, model.with_suffix(".onnx.json"), entry.config_sha256)
        urllib.request.urlretrieve(entry.model_card_url, temporary / "MODEL_CARD")
        (temporary / "LICENSE.txt").write_text(
            f"Voice: {entry.name}\nLicense: {entry.license}\n"
            f"Model card: {entry.model_card_url}\n",
            encoding="utf-8",
        )
        try:
            os.replace(temporary, target)
        except FileExistsError:
            shutil.rmtree(temporary)
        return target
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
