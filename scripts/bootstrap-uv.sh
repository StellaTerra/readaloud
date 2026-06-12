#!/bin/sh
set -eu

UV_VERSION=0.11.21
case "$(uname -m)" in
    x86_64)
        target=x86_64-unknown-linux-gnu
        sha256=8c88519b0ef0af9801fcdee419bbb12116bd9e6b18e162ae093c932d8b264050
        ;;
    aarch64|arm64)
        target=aarch64-unknown-linux-gnu
        sha256=88e800834007cc5efd4675f166eb2a51e7e3ad19876d85fa8805a6fb5c922397
        ;;
    *)
        echo "unsupported architecture: $(uname -m)" >&2
        exit 1
        ;;
esac

destination=${1:?usage: bootstrap-uv.sh DESTINATION}
archive=$(mktemp)
directory=$(mktemp -d)
trap 'rm -f "$archive"; rm -rf "$directory"' EXIT
url="https://github.com/astral-sh/uv/releases/download/$UV_VERSION/uv-$target.tar.gz"
curl -fL --proto '=https' --tlsv1.2 "$url" -o "$archive"
printf '%s  %s\n' "$sha256" "$archive" | sha256sum --check --status
tar -xzf "$archive" -C "$directory"
install -Dm755 "$directory/uv-$target/uv" "$destination"
