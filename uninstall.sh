#!/bin/sh
set -eu

data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}

systemctl --user disable --now readaloud.service 2>/dev/null || true
rm -f "$config_home/systemd/user/readaloud.service" "$HOME/.local/bin/readaloud"
systemctl --user daemon-reload
rm -rf "$data_home/readaloud/app" "$data_home/readaloud/tools" "$data_home/readaloud/python"
echo "Voices and configuration were retained."
echo "Remove $data_home/readaloud/voices and $config_home/readaloud manually to delete user data."
