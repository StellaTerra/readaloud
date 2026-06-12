from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from .audio import AudioFormat, AudioPlayer
from .config import Config
from .normalize import PlainTextNormalizer, TextNormalizer


class Voice(Protocol):
    def synthesize(self, text: str, syn_config: Any) -> Iterable[Any]: ...


@dataclass(frozen=True)
class SpeechStatus:
    state: str
    generation: int
    error: str | None = None


class SpeechEngine:
    def __init__(
        self,
        voice: Voice,
        config: Config,
        synthesis_config_factory: Callable[[Config], Any],
        player_factory: Callable[[str, float], AudioPlayer] = AudioPlayer,
        normalizer: TextNormalizer | None = None,
    ) -> None:
        self.voice = voice
        self.config = config
        self._make_syn_config = synthesis_config_factory
        self._player_factory = player_factory
        self._normalizer = normalizer or PlainTextNormalizer()
        self._generation = 0
        self._state = "idle"
        self._error: str | None = None
        self._player: AudioPlayer | None = None
        self._state_lock = threading.Lock()
        self._voice_lock = threading.Lock()

    def status(self) -> SpeechStatus:
        with self._state_lock:
            return SpeechStatus(self._state, self._generation, self._error)

    def speak(self, text: str) -> int:
        normalized = self._normalizer.normalize(text)
        generation = self.cancel()
        if not normalized:
            return generation
        with self._state_lock:
            self._state = "waiting"
            self._error = None
        threading.Thread(
            target=self._run,
            args=(generation, normalized),
            name=f"readaloud-speech-{generation}",
            daemon=True,
        ).start()
        return generation

    def cancel(self) -> int:
        with self._state_lock:
            self._generation += 1
            generation = self._generation
            player = self._player
            self._player = None
            self._state = "idle"
            self._error = None
        if player:
            player.cancel()
        return generation

    def _current(self, generation: int) -> bool:
        with self._state_lock:
            return generation == self._generation

    def _run(self, generation: int, text: str) -> None:
        player: AudioPlayer | None = None
        try:
            with self._voice_lock:
                if not self._current(generation):
                    return
                chunks = self.voice.synthesize(text, self._make_syn_config(self.config))
                stream = None
                audio_format = None
                chunk_index = 0
                for chunk in chunks:
                    if not self._current(generation):
                        return
                    current_format = AudioFormat(
                        chunk.sample_rate, chunk.sample_width, chunk.sample_channels
                    )
                    if stream is None:
                        audio_format = current_format
                        player = self._player_factory(
                            self.config.audio_backend, 1.0
                        )
                        stream = player.start(current_format)
                        with self._state_lock:
                            if generation != self._generation:
                                player.cancel()
                                return
                            self._player = player
                            self._state = "speaking"
                    elif current_format != audio_format:
                        raise RuntimeError("Piper changed audio format during synthesis")
                    if chunk_index:
                        silence_frames = round(
                            current_format.sample_rate
                            * self.config.sentence_silence
                        )
                        silence_bytes = (
                            silence_frames
                            * current_format.sample_width
                            * current_format.channels
                        )
                        stream.write(bytes(silence_bytes))
                    stream.write(chunk.audio_int16_bytes)
                    chunk_index += 1
                if player and self._current(generation):
                    player.finish()
        except Exception as error:
            if self._current(generation):
                with self._state_lock:
                    self._state = "error"
                    self._error = str(error)
            if player:
                player.cancel()
            return
        if self._current(generation):
            with self._state_lock:
                self._player = None
                self._state = "idle"
