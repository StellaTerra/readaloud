from pathlib import Path

import pytest

from readaloud.config import Config
from readaloud.piper_runtime import (
    load_voice,
    providers_for,
    require_active_provider,
)


def test_providers_for_cpu() -> None:
    assert providers_for(Config(execution_provider="cpu")) == ["CPUExecutionProvider"]


def test_providers_for_openvino_gpu() -> None:
    assert providers_for(Config(execution_provider="openvino-gpu")) == [
        ("OpenVINOExecutionProvider", {"device_type": "GPU"}),
        "CPUExecutionProvider",
    ]


def test_providers_for_openvino_auto() -> None:
    assert providers_for(Config(execution_provider="openvino-auto")) == [
        ("OpenVINOExecutionProvider", {"device_type": "AUTO"}),
        "CPUExecutionProvider",
    ]


def test_require_active_provider_rejects_missing_openvino() -> None:
    with pytest.raises(RuntimeError, match="OpenVINOExecutionProvider"):
        require_active_provider("openvino-gpu", ["CPUExecutionProvider"])


def test_load_voice_passes_configured_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    model.with_suffix(".onnx.json").write_text("{}", encoding="utf-8")
    captured = {}

    class Session:
        def __init__(self, path, sess_options, providers):
            captured["path"] = path
            captured["sess_options"] = sess_options
            captured["providers"] = providers

        def get_providers(self):
            return ["CPUExecutionProvider"]

    class SessionOptions:
        pass

    class PiperConfig:
        @staticmethod
        def from_dict(raw):
            captured["config"] = raw
            return "config"

    class PiperVoice:
        def __init__(self, **kwargs):
            captured["voice"] = kwargs

    runtime = type(
        "Runtime",
        (),
        {"InferenceSession": Session, "SessionOptions": SessionOptions},
    )
    fake = type(
        "FakePiperVoiceModule",
        (),
        {
            "onnxruntime": runtime,
            "PiperConfig": PiperConfig,
            "PiperVoice": PiperVoice,
            "ESPEAK_DATA_DIR": tmp_path,
        },
    )
    monkeypatch.setitem(__import__("sys").modules, "piper.voice", fake)

    load_voice(model, Config(execution_provider="cpu"))

    assert captured["path"] == str(model)
    assert captured["providers"] == ["CPUExecutionProvider"]
    assert captured["config"] == {}
    assert captured["voice"]["config"] == "config"
