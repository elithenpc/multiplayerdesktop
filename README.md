# MultiDesk

MultiDesk is an experimental collaborative desktop project. One Linux X11 computer shares its screen with browser clients, requests host approval, and displays a separate labelled cursor for each participant.

## Current implementation status

This first version is a screen-sharing and input prototype, not yet a true multi-pointer desktop.

- Browser clients can request access and wait for host approval.
- The host can approve or reject guests from a local admin page.
- Approved guests receive JPEG screen updates and can send pointer/keyboard events.
- Each guest has a separately rendered cursor overlay in the browser.
- Input is currently injected into the host's single X11 pointer/keyboard using xdotool. The guest cursor overlays are independent, but the underlying desktop pointer is not. Concurrent interactions therefore share one real pointer and can conflict.
- No hard participant cap is configured. Practical capacity depends on host CPU, network bandwidth and frame rate.

True simultaneous independent desktop pointers are not implemented yet. That requires XInput2 MPX master pointer/keyboard devices and per-device event injection, which is the next major engineering milestone. Do not treat the cursor overlays as proof of native MPX support.

## Requirements

- Linux Mint / Ubuntu running an X11 desktop session
- Python 3.10+
- xdotool, x11-utils
- A reachable network connection; Tailscale is recommended for private remote access

## Install

    git clone https://github.com/elithenpc/multiplayerdesktop.git
    cd multiplayerdesktop
    chmod +x install.sh
    ./install.sh

The installer creates a Python virtual environment and a private host configuration at ~/.config/multidesk/.

## Start

    cd ~/multiplayerdesktop
    source .venv/bin/activate
    python host.py

Open the printed host URL on the host computer and select Host dashboard. The first run prints an admin token in the terminal. Keep it private.

Guests open http://HOST-IP:8765, choose a display name and request access. The host approves them in the dashboard.

## Remote access

For a private Tailscale network, install and sign in to Tailscale on the host and guest computers, then open the host's Tailscale IP on port 8765.

For access by people outside your tailnet, use a properly configured HTTPS reverse proxy or Tailscale Funnel. Do not expose this prototype directly to the public internet without HTTPS and network-level access controls.

## Security notes

- The host approval gate is enabled by default.
- The admin token grants control over guest access. Do not share it.
- Approved guests can control the host desktop, including typing and clicking. Only approve people you trust.
- This prototype is intended for trusted networks and experimentation, not production deployment.

## Roadmap

1. Implement true XInput2 MPX pointer and keyboard devices, one per guest.
2. Route each guest's events to its own XInput2 device rather than the core pointer.
3. Replace periodic JPEG frames with WebRTC video and an SFU for scalable multi-viewer streaming.
4. Add HTTPS deployment, rate limiting, reconnection handling and per-session permissions.
5. Add participant limits and bandwidth controls configurable by the host.
