# readaloud

`readaloud` is a local Linux text-to-speech service built around Piper. It keeps
one voice model resident, accepts requests over a private Unix socket, and
replaces active speech instead of queueing it.

## Requirements

- A modern systemd Linux desktop on x86_64 or ARM64
- `curl`, `tar`, and `sha256sum` for installation
- PipeWire's `pw-play` or PulseAudio's `paplay`

The installer downloads pinned `uv 0.11.21`, a managed Python 3.12 runtime,
locked Python dependencies, and the checksum-locked default voice. Review
`scripts/bootstrap-uv.sh`, `uv.lock`, and `voices.lock.json` when upgrading
dependencies.

## Install

```sh
./install.sh
```

Installed application releases live under
`$XDG_DATA_HOME/readaloud/app/releases`; `current` is switched atomically. The
CLI shim is `~/.local/bin/readaloud`, and the service is a native systemd user
unit.

```sh
readaloud speak "Text to read"
printf '%s' "$text" | readaloud speak
readaloud cancel
readaloud status
readaloud config get
readaloud config set rate 50
readaloud voice list
readaloud voice install en_US-lessac-high
readaloud voice use en_US-lessac-high
readaloud doctor
```

Configuration is stored at
`$XDG_CONFIG_HOME/readaloud/config.toml`. Rate uses a `-100..100` scale and maps
to Piper's `length_scale` as `0.8 / (1 + rate / 100)`, clamped to `0.35..4.0`.

The socket protocol is newline-delimited JSON at
`$XDG_RUNTIME_DIR/readaloud/control.sock`. Requests include `"version": 1` and
one of the `speak`, `cancel`, `status`, or `reload` commands. Requests are
limited to 1 MiB and the socket is mode `0600`.

## Development

```sh
uv sync --frozen
uv run pytest
```

Piper synthesis already inside ONNX Runtime cannot be interrupted. Cancellation
terminates playback immediately; output arriving from the cancelled inference
is discarded, and the replacement starts at the next chunk boundary.

Voice licenses are independent of this project's GPL license. Every installed
voice retains its upstream `MODEL_CARD` and a visible license summary.

## Desktop shortcuts

The service deliberately does not read the clipboard or register global
shortcuts. Desktop integration is a small external wrapper that obtains text
from the current session and sends it to `readaloud`.

For X11, `examples/speak-selection-x11` uses the primary selection from
`xclip`. The first shortcut invocation speaks the selection; a second
invocation while speech is waiting or playing cancels it.

```sh
install -Dm755 examples/speak-selection-x11 \
    "$HOME/.local/bin/speak-selection"
```

Bind `~/.local/bin/speak-selection` in the desktop's keyboard settings. The
wrapper uses absolute paths where desktop shortcut environments commonly have
a restricted `PATH`.

On Wayland compositors that implement the primary-selection and data-control
protocols, including COSMIC, use the `wl-clipboard` wrapper:

```sh
install -Dm755 examples/speak-selection-wayland \
    "$HOME/.local/bin/speak-selection"
```

Bind `~/.local/bin/speak-selection` in the compositor's keyboard settings. On
COSMIC, add a custom shortcut under **Input Devices > Keyboard > Keyboard
Shortcuts**. The wrapper uses `wl-paste --primary --type text`; applications
must publish their selection through the Wayland primary-selection protocol.

Wayland does not provide one universal selection API. Compositors without
primary-selection or data-control support may require compositor-specific
clipboard tooling or a portal-aware helper. The socket protocol and service do
not otherwise depend on X11 or Wayland.

## Portability

The current implementation targets systemd user sessions and XDG paths. This
fits conventional distributions and Atomic desktops such as Fedora Silverblue
without writing into the immutable system image:

- application releases, managed Python, and voices live in
  `$XDG_DATA_HOME/readaloud`;
- configuration lives in `$XDG_CONFIG_HOME/readaloud`;
- the private control socket lives in `$XDG_RUNTIME_DIR/readaloud`;
- audio is sent to the user's PipeWire or PulseAudio session;
- the service unit is installed under the user's systemd configuration.

The installer still expects host `curl`, `tar`, `sha256sum`, systemd user
services, and either `pw-play` or `paplay`. Flatpak packaging and
desktop-specific Wayland selection helpers are intentionally deferred until
the service and protocol have had broader testing.
