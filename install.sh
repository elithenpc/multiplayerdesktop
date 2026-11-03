#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ "${XDG_SESSION_TYPE:-}" != "x11" ]]; then
  echo "ERROR: MultiDesk requires an X11 desktop session."
  echo "Log out, select the Cinnamon on Xorg/X11 session, and run this installer again."
  exit 1
fi

if [[ -z "${DISPLAY:-}" ]]; then
  echo "ERROR: DISPLAY is not set. Run this installer from your logged-in desktop terminal."
  exit 1
fi

sudo apt update
sudo apt install -y python3 python3-venv python3-pip xinput libx11-6 libxi6 libxtst6

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

mkdir -p "$HOME/.config/multidesk"
chmod 700 "$HOME/.config/multidesk"

echo
echo "MultiDesk dependencies installed."
echo "Start the host with:"
echo "  cd \"$ROOT\""
echo "  source .venv/bin/activate"
echo "  python host.py"
echo
echo "Keep the admin token printed by the host private."
