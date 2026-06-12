import asyncio
from pathlib import Path

from readaloud.config import Config
from readaloud.daemon import Server
from readaloud.protocol import request


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
