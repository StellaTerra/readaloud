from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

from .config import FIELDS, load, save, set_value
from .paths import config_path, socket_path, voices_dir
from .protocol import request
from .voices import install, installed, load_catalog


def catalog_path() -> Path:
    override = os.environ.get("READALOUD_VOICE_LOCK")
    if override:
        return Path(override)
    packaged = Path(str(files("readaloud").joinpath("voices.lock.json")))
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[2] / "voices.lock.json"


def call(command: str, **values: object) -> dict[str, object]:
    try:
        return asyncio.run(request(socket_path(), command, **values))
    except OSError as error:
        raise RuntimeError("readaloud service is not running") from error


def restart_service() -> None:
    subprocess.run(
        ["systemctl", "--user", "restart", "readaloud.service"],
        check=True,
    )


def doctor() -> int:
    problems = []
    try:
        config = load()
        print(f"config: ok ({config_path()})")
    except (OSError, ValueError) as error:
        problems.append(f"config: {error}")
        config = None
    for program in ("systemctl",):
        if not shutil.which(program):
            problems.append(f"missing host command: {program}")
    if not shutil.which("pw-play") and not shutil.which("paplay"):
        problems.append("missing audio backend: install pw-play or paplay")
    if config and not installed(config.voice):
        problems.append(f"voice not installed: {config.voice}")
    try:
        response = call("status")
        print(f"service: {response['state']}")
    except RuntimeError as error:
        problems.append(str(error))
    if problems:
        for problem in problems:
            print(f"problem: {problem}", file=sys.stderr)
        return 1
    print("doctor: all checks passed")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="readaloud")
    commands = root.add_subparsers(dest="command", required=True)
    speak = commands.add_parser("speak")
    speak.add_argument("text", nargs="?")
    commands.add_parser("cancel")
    commands.add_parser("status")
    config = commands.add_parser("config")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_get = config_commands.add_parser("get")
    config_get.add_argument("key", nargs="?")
    config_set = config_commands.add_parser("set")
    config_set.add_argument("key", choices=FIELDS)
    config_set.add_argument("value")
    voice = commands.add_parser("voice")
    voice_commands = voice.add_subparsers(dest="voice_command", required=True)
    voice_commands.add_parser("list")
    voice_install = voice_commands.add_parser("install")
    voice_install.add_argument("name")
    voice_use = voice_commands.add_parser("use")
    voice_use.add_argument("name")
    commands.add_parser("doctor")
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "speak":
            text = args.text if args.text is not None else sys.stdin.read()
            print(json.dumps(call("speak", text=text), ensure_ascii=False))
        elif args.command in {"cancel", "status"}:
            print(json.dumps(call(args.command), ensure_ascii=False))
        elif args.command == "config":
            config = load()
            if args.config_command == "get":
                values = config.__dict__
                print(values[args.key] if args.key else json.dumps(values, indent=2))
            else:
                updated = set_value(config, args.key, args.value)
                save(updated)
                try:
                    call("reload")
                except RuntimeError:
                    pass
        elif args.command == "voice":
            catalog = load_catalog(catalog_path())
            if args.voice_command == "list":
                for name, entry in catalog.items():
                    marker = "*" if installed(name) else " "
                    print(f"{marker} {name} ({entry.license})")
            elif args.voice_command == "install":
                if args.name not in catalog:
                    raise RuntimeError(f"voice is not in the catalog: {args.name}")
                print(install(catalog[args.name]))
            else:
                if args.name not in catalog:
                    raise RuntimeError(f"voice is not in the catalog: {args.name}")
                if not installed(args.name):
                    raise RuntimeError(f"voice is not installed: {args.name}")
                save(set_value(load(), "voice", args.name))
                restart_service()
        else:
            raise SystemExit(doctor())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"readaloud: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
