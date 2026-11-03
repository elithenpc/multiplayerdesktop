#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ "${XDG_SESSION_TYPE:-}" != "x11" ]]; then echo "Warning: this project targets X11; current session: ${XDG_SESSION_TYPE:-unknown}"; fi
sudo apt update
sudo apt install -y python3 python3-venv python3-pip xdotool x11-utils
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
mkdir -p "$HOME/.config/multidesk"
chmod 700 "$HOME/.config/multidesk"
echo "Installed. Start with: source .venv/bin/activate && python host.py"
