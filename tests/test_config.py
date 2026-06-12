from pathlib import Path

import pytest

from readaloud.config import Config, load, save, set_value


@pytest.mark.parametrize(
    ("rate", "expected"),
    [(-100, 4.0), (-50, 1.6), (0, 0.8), (50, 0.8 / 1.5), (100, 0.4)],
)
def test_rate_mapping(rate: int, expected: float) -> None:
    assert Config(rate=rate).length_scale == pytest.approx(expected)


def test_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    expected = Config(voice="voice", rate=-20, sentence_silence=0.2, volume=0.8)
    save(expected, path)
    assert load(path) == expected
    assert path.stat().st_mode & 0o777 == 0o600


def test_invalid_config_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("rate = 101\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load(path)
    with pytest.raises(ValueError):
        set_value(Config(), "rate", "-101")
