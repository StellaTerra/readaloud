from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Any

from .config import Config, load
from .engine import SpeechEngine
from .paths import runtime_dir, socket_path, voices_dir
from .protocol import MAX_REQUEST_BYTES, decode, encode
from .voices import model_path

LOG = logging.getLogger("readaloud")


def load_piper(config: Config, voice_file: Path | None = None) -> tuple[Any, Any]:
    from piper import PiperVoice, SynthesisConfig

    path = voice_file or model_path(config.voice)
    if not path.is_file() or not path.with_suffix(".onnx.json").is_file():
        raise RuntimeError(f"voice is not installed: {config.voice} ({path})")
    voice = PiperVoice.load(str(path))

    def synthesis_config(current: Config) -> SynthesisConfig:
        return SynthesisConfig(
            volume=current.volume,
            length_scale=current.length_scale,
        )

    return voice, synthesis_config


class Server:
    def __init__(self, engine: SpeechEngine, config: Config) -> None:
        self.engine = engine
        self.config = config

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            data = await reader.readline()
            if len(data) > MAX_REQUEST_BYTES or not data.endswith(b"\n"):
                raise ValueError("request exceeds 1 MiB or is not newline terminated")
            message = decode(data[:-1])
            command = message["command"]
            if command == "speak":
                generation = self.engine.speak(message["text"])
                response = {"ok": True, "generation": generation}
            elif command == "cancel":
                response = {"ok": True, "generation": self.engine.cancel()}
            elif command == "status":
                status = self.engine.status()
                response = {
                    "ok": True,
                    "state": status.state,
                    "generation": status.generation,
                    "error": status.error,
                    "voice": self.config.voice,
                }
            else:
                updated = load()
                if updated.voice != self.config.voice:
                    raise RuntimeError("voice changes require a service restart")
                self.config = updated
                self.engine.config = updated
                response = {"ok": True}
        except (ValueError, RuntimeError) as error:
            response = {"ok": False, "error": str(error)}
        writer.write(encode(response))
        await writer.drain()
        writer.close()
        await writer.wait_closed()


async def run_server(engine: SpeechEngine, config: Config, socket: Path) -> None:
    socket.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if socket.exists():
        socket.unlink()
    server = Server(engine, config)
    unix_server = await asyncio.start_unix_server(
        server.handle, socket, limit=MAX_REQUEST_BYTES + 1
    )
    os.chmod(socket, 0o600)
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(name, stop.set)
    try:
        async with unix_server:
            await stop.wait()
    finally:
        engine.cancel()
        unix_server.close()
        await unix_server.wait_closed()
        socket.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="readaloudd")
    parser.add_argument("--socket", type=Path, default=None)
    parser.add_argument("--voice-file", type=Path, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    config = load()
    voice, factory = load_piper(config, args.voice_file)
    engine = SpeechEngine(voice, config, factory)
    asyncio.run(run_server(engine, config, args.socket or socket_path()))


if __name__ == "__main__":
    main()
