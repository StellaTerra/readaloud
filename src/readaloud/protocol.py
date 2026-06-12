from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 1024 * 1024
VALID_COMMANDS = {"speak", "cancel", "status", "reload"}


def encode(message: dict[str, Any]) -> bytes:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"


def decode(data: bytes) -> dict[str, Any]:
    if len(data) > MAX_REQUEST_BYTES:
        raise ValueError("request exceeds 1 MiB")
    try:
        message = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid JSON request") from error
    if not isinstance(message, dict):
        raise ValueError("request must be a JSON object")
    if message.get("version") != PROTOCOL_VERSION:
        raise ValueError("unsupported protocol version")
    if message.get("command") not in VALID_COMMANDS:
        raise ValueError("unknown command")
    if message["command"] == "speak" and not isinstance(message.get("text"), str):
        raise ValueError("speak requires text")
    return message


async def request(socket: Path, command: str, **values: Any) -> dict[str, Any]:
    reader, writer = await asyncio.open_unix_connection(socket)
    try:
        writer.write(encode({"version": PROTOCOL_VERSION, "command": command, **values}))
        await writer.drain()
        line = await reader.readline()
        if not line:
            raise RuntimeError("service closed the connection without a response")
        response = json.loads(line)
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "service request failed"))
        return response
    finally:
        writer.close()
        await writer.wait_closed()
