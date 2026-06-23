import asyncio
import json
from pathlib import Path

import pytest

from readaloud.config import Config
from readaloud.daemon import Server
from readaloud.protocol import encode, request


class Engine:
    def __init__(self) -> None:
        self.config = Config()
        self.text = None
        self.generation = 0

    def speak(self, text: str) -> int:
        self.text = text
        self.generation += 1
        return self.generation

    def cancel(self) -> int:
        self.generation += 1
        return self.generation

    def status(self):
        return type("Status", (), {"state": "idle", "generation": self.generation, "error": None})()


def test_socket_round_trip(tmp_path: Path) -> None:
    async def run() -> None:
        engine = Engine()
        server = await asyncio.start_unix_server(
            Server(engine, Config()).handle, tmp_path / "control.sock"
        )
        async with server:
            response = await request(tmp_path / "control.sock", "speak", text="line 1\n世界")
        assert response["generation"] == 1
        assert engine.text == "line 1\n世界"

    asyncio.run(run())


def test_status_reports_execution_provider(tmp_path: Path) -> None:
    async def run() -> None:
        engine = Engine()
        config = Config(execution_provider="cpu")
        server = await asyncio.start_unix_server(
            Server(engine, config).handle, tmp_path / "control.sock"
        )
        async with server:
            response = await request(tmp_path / "control.sock", "status")
        assert response["execution_provider"] == "cpu"

    asyncio.run(run())


def test_reload_rejects_execution_provider_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def run() -> None:
        engine = Engine()
        monkeypatch.setattr(
            "readaloud.daemon.load",
            lambda: Config(execution_provider="openvino-auto"),
        )
        server = await asyncio.start_unix_server(
            Server(engine, Config(execution_provider="cpu")).handle,
            tmp_path / "control.sock",
        )
        async with server:
            reader, writer = await asyncio.open_unix_connection(
                tmp_path / "control.sock"
            )
            writer.write(encode({"version": 1, "command": "reload"}))
            await writer.drain()
            response = json.loads(await reader.readline())
            writer.close()
            await writer.wait_closed()
        assert response["ok"] is False
        assert "execution provider changes require a service restart" in response["error"]

    asyncio.run(run())
