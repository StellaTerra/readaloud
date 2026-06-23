import threading
import time
from dataclasses import dataclass

from readaloud.config import Config
from readaloud.engine import SpeechEngine, split_speech_units


@dataclass
class Chunk:
    audio_int16_bytes: bytes
    sample_rate: int = 22050
    sample_width: int = 2
    sample_channels: int = 1


class Voice:
    def __init__(
        self,
        gate: threading.Event | None = None,
        *,
        suffix_chunk: bytes | None = b"-stale",
    ) -> None:
        self.calls: list[str] = []
        self.gate = gate
        self.suffix_chunk = suffix_chunk

    def synthesize(self, text: str, syn_config: object):
        self.calls.append(text)
        yield Chunk(text.encode())
        if self.gate:
            self.gate.wait(1)
        if self.suffix_chunk is not None:
            yield Chunk(self.suffix_chunk)


class Player:
    instances: list["Player"] = []

    def __init__(self, backend: str, volume: float) -> None:
        self.data = bytearray()
        self.cancelled = False
        self.finished = False
        Player.instances.append(self)

    def start(self, audio: object):
        return self

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    def finish(self) -> None:
        self.finished = True

    def cancel(self) -> None:
        self.cancelled = True


def wait_idle(engine: SpeechEngine) -> None:
    deadline = time.monotonic() + 1
    while engine.status().state != "idle" and time.monotonic() < deadline:
        time.sleep(0.005)


def wait_for(predicate) -> None:
    deadline = time.monotonic() + 1
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.005)
    assert predicate()


def test_split_speech_units_splits_clear_sentence_endings() -> None:
    assert split_speech_units("First. Second? Third!") == [
        "First.",
        "Second?",
        "Third!",
    ]


def test_split_speech_units_splits_blank_paragraphs() -> None:
    assert split_speech_units("First paragraph\n\nSecond paragraph") == [
        "First paragraph",
        "Second paragraph",
    ]


def test_split_speech_units_keeps_abbreviations_and_initialisms() -> None:
    assert split_speech_units("Dr. Smith visited the U.S. Embassy. He left.") == [
        "Dr. Smith visited the U.S. Embassy.",
        "He left.",
    ]
    assert split_speech_units("Use e.g. apples, oranges, etc. for examples.") == [
        "Use e.g. apples, oranges, etc. for examples."
    ]


def test_split_speech_units_handles_quotes_and_brackets() -> None:
    assert split_speech_units('She said "Go!" (Then left.) Next?') == [
        'She said "Go!"',
        "(Then left.)",
        "Next?",
    ]


def test_passage_uses_per_sentence_voice_calls_and_one_player() -> None:
    Player.instances.clear()
    voice = Voice(suffix_chunk=None)
    engine = SpeechEngine(
        voice, Config(sentence_silence=0), lambda _: object(), Player
    )
    engine.speak("First. Second.")
    wait_idle(engine)
    assert voice.calls == ["First.", "Second."]
    assert len(Player.instances) == 1
    assert Player.instances[0].data == b"First.Second."
    assert Player.instances[0].finished


def test_replacement_cancels_player_and_discards_stale_audio() -> None:
    Player.instances.clear()
    gate = threading.Event()
    voice = Voice(gate)
    engine = SpeechEngine(
        voice, Config(sentence_silence=0), lambda _: object(), Player
    )
    engine.speak("old")
    wait_for(lambda: Player.instances)
    engine.speak("new")
    assert Player.instances[0].cancelled
    gate.set()
    wait_idle(engine)
    assert Player.instances[0].data == b"old"
    assert Player.instances[-1].data == b"new-stale"


def test_empty_text_cancels() -> None:
    Player.instances.clear()
    gate = threading.Event()
    engine = SpeechEngine(
        Voice(gate),
        Config(sentence_silence=0),
        lambda _: object(),
        Player,
    )
    engine.speak("active")
    wait_for(lambda: Player.instances)
    engine.speak(" \n ")
    gate.set()
    assert engine.status().state == "idle"
    assert Player.instances[0].cancelled


def test_sentence_silence_is_written_to_same_stream() -> None:
    Player.instances.clear()
    voice = Voice()
    engine = SpeechEngine(
        voice, Config(sentence_silence=0.01), lambda _: object(), Player
    )
    engine.speak("two sentences")
    wait_idle(engine)
    expected_silence = bytes(round(22050 * 0.01) * 2)
    assert Player.instances[0].data == b"two sentences" + expected_silence + b"-stale"
    assert len(expected_silence) % 2 == 0


def test_sentence_boundaries_remain_aligned_for_default_silence() -> None:
    Player.instances.clear()
    voice = Voice(suffix_chunk=None)
    engine = SpeechEngine(voice, Config(), lambda _: object(), Player)
    engine.speak("First. Second.")
    wait_idle(engine)
    silence_size = round(22050 * Config().sentence_silence) * 2
    assert silence_size == 2204
    assert Player.instances[0].data == b"First." + bytes(silence_size) + b"Second."


def test_synthesizes_next_unit_while_first_audio_is_still_writing() -> None:
    class SlowFirstWritePlayer(Player):
        first_write_started = threading.Event()
        release_first_write = threading.Event()

        def write(self, data: bytes) -> None:
            if not self.data:
                self.first_write_started.set()
                self.release_first_write.wait(1)
            super().write(data)

    Player.instances.clear()
    SlowFirstWritePlayer.first_write_started.clear()
    SlowFirstWritePlayer.release_first_write.clear()
    voice = Voice(suffix_chunk=None)
    engine = SpeechEngine(
        voice, Config(sentence_silence=0), lambda _: object(), SlowFirstWritePlayer
    )
    engine.speak("First. Second.")
    wait_for(lambda: SlowFirstWritePlayer.first_write_started.is_set())
    wait_for(lambda: voice.calls == ["First.", "Second."])
    assert not Player.instances[0].finished
    SlowFirstWritePlayer.release_first_write.set()
    wait_idle(engine)


def test_cancel_after_blocking_synthesis_discards_stale_audio() -> None:
    class BlockingVoice(Voice):
        entered = threading.Event()
        release = threading.Event()

        def synthesize(self, text: str, syn_config: object):
            self.calls.append(text)
            self.entered.set()
            self.release.wait(1)
            yield Chunk(text.encode())

    Player.instances.clear()
    BlockingVoice.entered.clear()
    BlockingVoice.release.clear()
    voice = BlockingVoice(suffix_chunk=None)
    engine = SpeechEngine(
        voice, Config(sentence_silence=0), lambda _: object(), Player
    )
    engine.speak("old")
    wait_for(lambda: BlockingVoice.entered.is_set())
    engine.cancel()
    BlockingVoice.release.set()
    wait_idle(engine)
    assert Player.instances == []


def test_queue_limit_prevents_synthesizing_all_units_far_ahead() -> None:
    class SlowFirstWritePlayer(Player):
        first_write_started = threading.Event()
        release_first_write = threading.Event()

        def write(self, data: bytes) -> None:
            if not self.data:
                self.first_write_started.set()
                self.release_first_write.wait(1)
            super().write(data)

    Player.instances.clear()
    SlowFirstWritePlayer.first_write_started.clear()
    SlowFirstWritePlayer.release_first_write.clear()
    voice = Voice(suffix_chunk=None)
    engine = SpeechEngine(
        voice, Config(sentence_silence=0), lambda _: object(), SlowFirstWritePlayer
    )
    engine.speak("One. Two. Three. Four.")
    wait_for(lambda: SlowFirstWritePlayer.first_write_started.is_set())
    time.sleep(0.05)
    assert voice.calls == ["One.", "Two.", "Three."]
    SlowFirstWritePlayer.release_first_write.set()
    wait_idle(engine)
    assert voice.calls == ["One.", "Two.", "Three.", "Four."]
