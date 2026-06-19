from __future__ import annotations

import shutil
import subprocess
import threading
from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True)
class AudioFormat:
    sample_rate: int
    sample_width: int
    channels: int


class AudioPlayer:
    def __init__(self, backend: str = "auto", volume: float = 1.0) -> None:
        self.backend = backend
        self.volume = volume
        self._process: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()

    def _command(self, audio: AudioFormat) -> list[str]:
        if audio.sample_width != 2:
            raise RuntimeError(f"unsupported sample width: {audio.sample_width}")
        backend = self.backend
        if backend == "auto":
            backend = "pipewire" if shutil.which("pw-play") else "pulse"
        if backend == "pipewire" and shutil.which("pw-play"):
            return [
                "pw-play", "--raw", "--rate", str(audio.sample_rate),
                "--channels", str(audio.channels), "--format", "s16",
                "--volume", str(min(1.0, self.volume)), "--latency", "50ms", "-",
            ]
        if backend == "pulse" and shutil.which("paplay"):
            return [
                "paplay", "--raw", f"--rate={audio.sample_rate}",
                f"--channels={audio.channels}", "--format=s16le",
                f"--volume={round(min(1.0, self.volume) * 65536)}",
                "--latency-msec=50",
            ]
        raise RuntimeError(f"audio backend unavailable: {backend}")

    def start(self, audio: AudioFormat) -> BinaryIO:
        process = subprocess.Popen(
            self._command(audio),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        with self._lock:
            self._process = process
        assert process.stdin is not None
        return process.stdin

    def finish(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
        if not process:
            return
        if process.stdin:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
        process.wait()

    def cancel(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
