from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from .config import Config

Provider = str | tuple[str, dict[str, str]]


def providers_for(config: Config) -> list[Provider]:
    if config.execution_provider == "cpu":
        return ["CPUExecutionProvider"]
    if config.execution_provider == "openvino-gpu":
        return [
            ("OpenVINOExecutionProvider", {"device_type": "GPU"}),
            "CPUExecutionProvider",
        ]
    if config.execution_provider == "openvino-auto":
        return [
            ("OpenVINOExecutionProvider", {"device_type": "AUTO"}),
            "CPUExecutionProvider",
        ]
    raise ValueError(f"unsupported execution provider: {config.execution_provider}")


def require_active_provider(configured: str, active: list[str]) -> None:
    if configured == "cpu":
        if "CPUExecutionProvider" not in active:
            raise RuntimeError("CPUExecutionProvider is not active")
        return
    if "OpenVINOExecutionProvider" not in active:
        available = ", ".join(active) or "none"
        raise RuntimeError(
            f"{configured} requires OpenVINOExecutionProvider, active providers: "
            f"{available}"
        )


def load_voice(model_path: Path, config: Config) -> Any:
    piper_voice = importlib.import_module("piper.voice")

    config_path = model_path.with_suffix(".onnx.json")
    with config_path.open("r", encoding="utf-8") as config_file:
        config_dict = json.load(config_file)

    session = piper_voice.onnxruntime.InferenceSession(
        str(model_path),
        sess_options=piper_voice.onnxruntime.SessionOptions(),
        providers=providers_for(config),
    )
    active = list(session.get_providers())
    require_active_provider(config.execution_provider, active)
    return piper_voice.PiperVoice(
        config=piper_voice.PiperConfig.from_dict(config_dict),
        session=session,
        espeak_data_dir=Path(piper_voice.ESPEAK_DATA_DIR),
        download_dir=Path.cwd(),
    )
