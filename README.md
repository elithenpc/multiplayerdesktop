# MultiDesk

MultiDesk lets several people connect to one Linux X11 desktop from a browser. Each approved guest receives a separate XInput2 MPX master pointer and keyboard, plus a live WebRTC video stream.

## Features

- Browser clients work on Windows, macOS and Linux. No client installation is required.
- Live desktop video using WebRTC with VP8 encoding and browser-native playback.
- Socket.IO is used for signalling and input events. Video travels over a direct WebRTC media connection.
- Host approval, independent native X11 cursors and keyboards, mouse, drag, scroll and keyboard input.
- Guest video sessions and virtual devices are removed when guests disconnect.
- Real participant capacity depends on host CPU, video encoding load, upload bandwidth and network conditions.

## Compatibility

Requires Xorg/X11 with XInput2 MPX support. Wayland is not supported. Some applications do not handle multiple master pointers perfectly.

## Install on Linux Mint

Run these commands in your logged-in Cinnamon X11 session:

    git clone https://github.com/elithenpc/multiplayerdesktop.git
    cd multiplayerdesktop
    bash install.sh

The installer installs Python packages system-wide. It does not create or use a virtual environment.

## Start

    cd ~/multiplayerdesktop
    python3 host.py

The terminal prints the guest URL, Tailscale URL if available, host dashboard URL and admin token. Keep the token private. Guests request access in the browser; approve them from the dashboard. Run the host as your logged-in desktop user, never with sudo.

## WebRTC networking

The web page and Socket.IO signalling can be reached over LAN, Tailscale or Tailscale Funnel. WebRTC video is a separate peer-to-peer UDP connection. Funnel publishes the web/signalling service but does not relay video media.

Google's public STUN server is used by default. STUN works on many home networks but cannot guarantee connectivity through every NAT, firewall or carrier network. For reliable connections between arbitrary networks, configure a TURN relay:

    export MULTIDESK_TURN_URL="turn:YOUR-TURN-HOST:3478?transport=udp"
    export MULTIDESK_TURN_USERNAME="YOUR-TURN-USERNAME"
    export MULTIDESK_TURN_PASSWORD="YOUR-TURN-CREDENTIAL"
    python3 host.py

Use credentials from a TURN provider or your own coturn server. Keep credentials private. TURN carries the video traffic, so relay bandwidth capacity matters. For Tailscale-only use, try direct connectivity first and add TURN if ICE fails.

Do not expose the host dashboard token. Approved guests can control the computer.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| MULTIDESK_HOST | 0.0.0.0 | Web/signalling bind address |
| MULTIDESK_PORT | 8765 | Web/signalling port |
| MULTIDESK_STUN_URL | stun:stun.l.google.com:19302 | STUN server |
| MULTIDESK_TURN_URL | unset | Comma-separated TURN URLs |
| MULTIDESK_TURN_USERNAME | unset | TURN username |
| MULTIDESK_TURN_PASSWORD | unset | TURN credential |

## Troubleshooting

- Requires X11. Choose Cinnamon on Xorg/X11 at login.
- Start from a terminal in the logged-in desktop session, not sudo.
- If MPX creation fails, check that xinput can create master devices.
- If video fails, inspect the host terminal and browser console. Some networks require TURN because STUN cannot traverse their NAT/firewall.
- The host desktop must be unlocked and visible.
