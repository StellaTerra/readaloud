#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
config_home=${XDG_CONFIG_HOME:-"$HOME/.config"}
app_root="$data_home/readaloud/app"
tools_root="$data_home/readaloud/tools"
build_id=$(
    find "$project_dir/src" "$project_dir/packaging" -type f \
        ! -path '*/__pycache__/*' ! -name '*.pyc' -print |
        sort |
        xargs sha256sum
    sha256sum "$project_dir/pyproject.toml" "$project_dir/uv.lock" \
        "$project_dir/voices.lock.json"
)
build_id=$(printf '%s\n' "$build_id" | sha256sum | cut -c1-12)
release="0.1.0-$build_id"
release_dir="$app_root/releases/$release"
uv="$tools_root/uv-0.11.21"

command -v systemctl >/dev/null || { echo "systemctl is required" >&2; exit 1; }
if ! command -v pw-play >/dev/null && ! command -v paplay >/dev/null; then
    echo "pw-play or paplay is required" >&2
    exit 1
fi

mkdir -p "$tools_root" "$app_root/releases" "$config_home/readaloud" "$HOME/.local/bin" "$config_home/systemd/user"
if [ ! -x "$uv" ]; then
    "$project_dir/scripts/bootstrap-uv.sh" "$uv"
fi

staging="$app_root/releases/.staging-$release-$$"
rm -rf "$staging"
mkdir -p "$staging"
cp -R "$project_dir/src" "$project_dir/packaging" "$staging/"
cp "$project_dir/pyproject.toml" "$project_dir/uv.lock" "$project_dir/voices.lock.json" \
    "$project_dir/README.md" "$project_dir/CONTRIBUTING.md" \
    "$project_dir/LICENSE" "$staging/"
find "$staging" -type d -name __pycache__ -prune -exec rm -rf {} +
if [ ! -x "$release_dir/.venv/bin/readaloud" ]; then
    rm -rf "$release_dir"
    mv "$staging" "$release_dir"
    UV_PYTHON_INSTALL_DIR="$data_home/readaloud/python" "$uv" python install 3.12
    UV_PYTHON_INSTALL_DIR="$data_home/readaloud/python" "$uv" sync \
        --project "$release_dir" --frozen --no-dev --python 3.12
else
    rm -rf "$staging"
fi
ln -sfn "$release_dir" "$app_root/current.new"
mv -Tf "$app_root/current.new" "$app_root/current"

cat >"$HOME/.local/bin/readaloud" <<EOF
#!/bin/sh
exec "$app_root/current/.venv/bin/readaloud" "\$@"
EOF
chmod 755 "$HOME/.local/bin/readaloud"
install -m644 "$project_dir/packaging/systemd/readaloud.service" "$config_home/systemd/user/readaloud.service"

if [ ! -f "$config_home/readaloud/config.toml" ]; then
    "$HOME/.local/bin/readaloud" config set voice en_US-lessac-high
fi
"$HOME/.local/bin/readaloud" voice install en_US-lessac-high
systemctl --user daemon-reload
systemctl --user enable readaloud.service
systemctl --user restart readaloud.service
attempt=0
while ! "$HOME/.local/bin/readaloud" status >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        echo "readaloud service did not become ready within 15 seconds" >&2
        systemctl --user status readaloud.service --no-pager >&2 || true
        exit 1
    fi
    sleep 0.5
done
"$HOME/.local/bin/readaloud" doctor
