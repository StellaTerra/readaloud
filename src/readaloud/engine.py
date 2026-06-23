from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from queue import Empty, Full, Queue
from time import sleep
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


@dataclass(frozen=True)
class _AudioChunk:
    audio_format: AudioFormat
    data: bytes


@dataclass(frozen=True)
class _SynthesisError:
    error: Exception


_QUEUE_END = object()
_TRAILING_CLOSERS = "\"')]}"
_ABBREVIATIONS = {
    "mr.",
    "mrs.",
    "ms.",
    "dr.",
    "prof.",
    "sr.",
    "jr.",
    "st.",
    "vs.",
    "etc.",
    "e.g.",
    "i.e.",
}


def split_speech_units(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    units: list[str] = []
    start = 0
    index = 0
    while index < len(normalized):
        if normalized[index] == "\n":
            after_break = _blank_break_end(normalized, index)
            if after_break is not None:
                _append_unit(units, normalized[start:index])
                start = after_break
                index = after_break
                continue
        if normalized[index] in ".?!" and _is_sentence_boundary(normalized, index):
            end = index + 1
            while end < len(normalized) and normalized[end] in _TRAILING_CLOSERS:
                end += 1
            _append_unit(units, normalized[start:end])
            start = end
            index = end
            continue
        index += 1
    _append_unit(units, normalized[start:])
    return units


def _append_unit(units: list[str], text: str) -> None:
    unit = text.strip()
    if unit:
        units.append(unit)


def _blank_break_end(text: str, index: int) -> int | None:
    cursor = index
    newlines = 0
    while cursor < len(text) and text[cursor].isspace():
        if text[cursor] == "\n":
            newlines += 1
        cursor += 1
        if newlines >= 2:
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            return cursor
    return None


def _is_sentence_boundary(text: str, index: int) -> bool:
    if text[index] == "." and _is_abbreviation_period(text, index):
        return False
    after = index + 1
    while after < len(text) and text[after] in _TRAILING_CLOSERS:
        after += 1
    return after == len(text) or text[after].isspace()


def _is_abbreviation_period(text: str, index: int) -> bool:
    start = index
    while start > 0 and (text[start - 1].isalpha() or text[start - 1] == "."):
        start -= 1
    token = text[start : index + 1].lower()
    if token in _ABBREVIATIONS:
        return True
    parts = token.split(".")
    return (
        len(parts) > 2
        and parts[-1] == ""
        and all(len(part) == 1 and part.isalpha() for part in parts[:-1])
    )


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
        units = split_speech_units(text)
        if not units:
            return
        audio_queue: Queue[object] = Queue(maxsize=2)
        threading.Thread(
            target=self._synthesize,
            args=(generation, units, audio_queue),
            name=f"readaloud-synthesis-{generation}",
            daemon=True,
        ).start()
        self._play(generation, audio_queue)

    def _synthesize(
        self, generation: int, units: list[str], audio_queue: Queue[object]
    ) -> None:
        try:
            syn_config = self._make_syn_config(self.config)
            with self._voice_lock:
                for unit in units:
                    if not self._current(generation):
                        return
                    if not self._wait_for_queue_capacity(generation, audio_queue):
                        return
                    chunks = self.voice.synthesize(unit, syn_config)
                    for chunk in chunks:
                        if not self._current(generation):
                            return
                        audio = _AudioChunk(
                            AudioFormat(
                                chunk.sample_rate,
                                chunk.sample_width,
                                chunk.sample_channels,
                            ),
                            chunk.audio_int16_bytes,
                        )
                        if not self._put_audio(generation, audio_queue, audio):
                            return
        except Exception as error:
            self._put_audio(generation, audio_queue, _SynthesisError(error))
        finally:
            self._put_audio(generation, audio_queue, _QUEUE_END)

    def _wait_for_queue_capacity(
        self, generation: int, audio_queue: Queue[object]
    ) -> bool:
        while self._current(generation):
            if not audio_queue.full():
                return True
            sleep(0.01)
        return False

    def _put_audio(
        self, generation: int, audio_queue: Queue[object], item: object
    ) -> bool:
        while self._current(generation):
            try:
                audio_queue.put(item, timeout=0.01)
                return self._current(generation)
            except Full:
                pass
        return False

    def _play(self, generation: int, audio_queue: Queue[object]) -> None:
        player: AudioPlayer | None = None
        try:
            stream = None
            audio_format = None
            chunk_index = 0
            while self._current(generation):
                try:
                    item = audio_queue.get(timeout=0.01)
                except Empty:
                    continue
                if item is _QUEUE_END:
                    break
                if isinstance(item, _SynthesisError):
                    raise item.error
                assert isinstance(item, _AudioChunk)
                if not self._current(generation):
                    return
                current_format = item.audio_format
                if stream is None:
                    audio_format = current_format
                    player = self._player_factory(self.config.audio_backend, 1.0)
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
                        current_format.sample_rate * self.config.sentence_silence
                    )
                    silence_bytes = (
                        silence_frames
                        * current_format.sample_width
                        * current_format.channels
                    )
                    if not self._current(generation):
                        return
                    stream.write(bytes(silence_bytes))
                if not self._current(generation):
                    return
                stream.write(item.data)
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
