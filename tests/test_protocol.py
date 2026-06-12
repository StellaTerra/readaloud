import json

import pytest

from readaloud.protocol import MAX_REQUEST_BYTES, decode, encode


def test_protocol_accepts_unicode_and_multiline() -> None:
    text = "Hello\nΚαλημέρα 世界"
    message = decode(encode({"version": 1, "command": "speak", "text": text})[:-1])
    assert message["text"] == text


def test_protocol_rejects_oversized_request() -> None:
    with pytest.raises(ValueError, match="1 MiB"):
        decode(b"x" * (MAX_REQUEST_BYTES + 1))


@pytest.mark.parametrize(
    "message",
    [
        {"version": 2, "command": "status"},
        {"version": 1, "command": "unknown"},
        {"version": 1, "command": "speak", "text": 4},
    ],
)
def test_protocol_rejects_invalid_messages(message: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        decode(json.dumps(message).encode())
