from __future__ import annotations

from typing import Protocol


class TextNormalizer(Protocol):
    def normalize(self, text: str) -> str: ...


class PlainTextNormalizer:
    def normalize(self, text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n").strip()
