from readaloud.audio import AudioFormat, AudioPlayer


def test_pipewire_plays_raw_pcm(monkeypatch) -> None:
    monkeypatch.setattr("readaloud.audio.shutil.which", lambda name: f"/usr/bin/{name}")

    command = AudioPlayer("pipewire", 0.75)._command(AudioFormat(22050, 2, 1))

    assert command == [
        "pw-play",
        "--raw",
        "--rate",
        "22050",
        "--channels",
        "1",
        "--format",
        "s16",
        "--volume",
        "0.75",
        "--latency",
        "50ms",
        "-",
    ]


def test_pulse_plays_raw_pcm(monkeypatch) -> None:
    monkeypatch.setattr("readaloud.audio.shutil.which", lambda name: f"/usr/bin/{name}")

    command = AudioPlayer("pulse", 0.5)._command(AudioFormat(22050, 2, 1))

    assert command == [
        "paplay",
        "--raw",
        "--rate=22050",
        "--channels=1",
        "--format=s16le",
        "--volume=32768",
        "--latency-msec=50",
    ]
