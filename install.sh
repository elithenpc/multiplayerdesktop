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
sudo apt install -y python3 python3-pip python3-numpy python3-pil python3-gi gir1.2-gtk-3.0 python3-cairo xinput libx11-6 libxi6 libxtst6 libxcursor1 pkg-config python3-dev build-essential

python3 -m pip install --break-system-packages --upgrade -r requirements.txt

mkdir -p "$HOME/.config/multidesk"
chmod 700 "$HOME/.config/multidesk"

echo
echo "MultiDesk dependencies installed."
echo "Start the host with:"
echo "  cd \"$ROOT\""
echo "  python3 host.py"
echo
echo "Keep the admin token printed by the host private."
