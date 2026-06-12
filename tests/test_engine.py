import threading
import time
from dataclasses import dataclass

from readaloud.config import Config
from readaloud.engine import SpeechEngine


@dataclass
class Chunk:
    audio_int16_bytes: bytes
    sample_rate: int = 22050
    sample_width: int = 2
    sample_channels: int = 1


class Voice:
    def __init__(self, gate: threading.Event | None = None) -> None:
        self.calls: list[str] = []
        self.gate = gate

    def synthesize(self, text: str, syn_config: object):
        self.calls.append(text)
        yield Chunk(text.encode())
        if self.gate:
            self.gate.wait(1)
        yield Chunk(b"-stale")


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


def test_passage_uses_one_voice_and_one_player() -> None:
    Player.instances.clear()
    voice = Voice()
    engine = SpeechEngine(
        voice, Config(sentence_silence=0), lambda _: object(), Player
    )
    engine.speak("First. Second.")
    wait_idle(engine)
    assert voice.calls == ["First. Second."]
    assert len(Player.instances) == 1
    assert Player.instances[0].data == b"First. Second.-stale"
    assert Player.instances[0].finished


def test_replacement_cancels_player_and_discards_stale_audio() -> None:
    Player.instances.clear()
    gate = threading.Event()
    voice = Voice(gate)
    engine = SpeechEngine(
        voice, Config(sentence_silence=0), lambda _: object(), Player
    )
    engine.speak("old")
    deadline = time.monotonic() + 1
    while not Player.instances and time.monotonic() < deadline:
        time.sleep(0.005)
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
        Voice(gate), Config(sentence_silence=0), lambda _: object(), Player
    )
    engine.speak("active")
    deadline = time.monotonic() + 1
    while not Player.instances and time.monotonic() < deadline:
        time.sleep(0.005)
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
    voice = Voice()
    engine = SpeechEngine(voice, Config(), lambda _: object(), Player)
    engine.speak("First. Second.")
    wait_idle(engine)
    silence_size = round(22050 * Config().sentence_silence) * 2
    assert silence_size == 2204
    assert Player.instances[0].data == (
        b"First. Second." + bytes(silence_size) + b"-stale"
    )
