# Contributing

Use Python 3.12 and the frozen `uv.lock`. Keep protocol changes backward
compatible or increment the protocol version. Dependency and voice catalog
updates must be explicit, reviewed changes with updated checksums.

Run `uv run pytest` before submitting changes. Hardware acceptance should cover
Linux Mint and an atomic systemd desktop such as Fedora Silverblue.

Do not add clipboard, selection, or desktop-shortcut dependencies to the
daemon. Keep those session-specific concerns in small wrappers under
`examples/`.
