# MultiDesk

MultiDesk lets several people connect to one Linux X11 desktop from a browser. Each approved guest receives a separate XInput2 MPX master pointer and keyboard, so their cursor and typing device are distinct from the host and other guests.

## Features in this version

- Browser clients work on Windows, macOS and Linux. No client installation is required.
- One shared view of the host's X11 desktop.
- Host approval required for every connection.
- Per-guest XInput2 master pointer and master keyboard devices.
- Separate native desktop cursors, with guest cursor labels overlaid in the browser view.
- Mouse movement, left/middle/right click, drag, scroll and keyboard events.
- Guests are disconnected and their virtual devices removed when they leave.
- No hard-coded participant cap. Real capacity depends on host CPU, upload bandwidth, screen resolution and the applications being shared.
- JPEG screen streaming over Socket.IO/WebSocket. WebRTC/SFU transport is a future performance milestone.

## Important compatibility note

This relies on Xorg/X11 with XInput2 MPX support. It does not work in a Wayland session. Some desktop applications and older toolkits do not handle multiple master pointers perfectly; GTK/XInput2-aware applications generally have better multi-device behaviour than software written only for the traditional single-pointer model. Test the applications you intend to share.

This project creates actual X11 master devices. It does not fake independent cursors with browser overlays or route every guest through one shared mouse.

## Install on Linux Mint

Use a terminal in your logged-in Cinnamon X11 session:

    git clone https://github.com/elithenpc/multiplayerdesktop.git
    cd multiplayerdesktop
    bash install.sh

The installer installs the XInput runtime tools/libraries and creates a Python virtual environment.

## Start the host

    cd ~/multiplayerdesktop
    source .venv/bin/activate
    python host.py

The terminal prints:
- Guest URL for your local network
- Tailscale URL if Tailscale is installed and connected
- Host dashboard URL
- A randomly generated admin token

Keep the admin token private. Open the dashboard on the host computer and paste in the token. Guests open the guest URL, enter a display name and request access. Approve each guest from the dashboard.

The server must run as the logged-in desktop user, not with sudo. It needs access to that user's X11 display to create and control MPX devices.

## Remote connections

### Devices on your Wi-Fi or LAN

Open the guest URL printed by the host on another computer on the same network.

### Private Tailscale access

Install and sign in to Tailscale on the host and guest computers. Open the Tailscale guest URL printed by MultiDesk. Only devices on your tailnet can reach it.

### Friends outside your tailnet

Tailscale Funnel can publish the host service to the public internet with HTTPS. After enabling Funnel in your tailnet policy, run this on the host while MultiDesk is running:

    sudo tailscale funnel --bg 8765
    tailscale funnel status

Copy the HTTPS URL shown by the status command and share it with guests. The host approval screen still controls who gets desktop input access. Funnel requires MagicDNS and HTTPS certificates to be enabled for your tailnet. To remove the Funnel configuration later, run:

    sudo tailscale funnel reset

Do not forward port 8765 directly from your router to the internet. Do not publish the host dashboard token. If using another public reverse proxy, it must support WebSocket upgrades and HTTPS.

## Security

Approved guests can control the host computer. Only approve people you trust. Keep the host admin token private. Revoke a guest or stop the server to end access. This is an early-stage project and has not had an independent security audit; use trusted networks and do not treat it as a hardened public remote-desktop service.

## Configuration

Environment variables:

| Variable | Default | Purpose |
|---|---:|---|
| MULTIDESK_HOST | 0.0.0.0 | Bind address |
| MULTIDESK_PORT | 8765 | Listening port |
| MULTIDESK_FPS | 6 | Screen update rate, clamped to 1–12 |
| MULTIDESK_JPEG_QUALITY | 62 | JPEG quality, clamped to 35–85 |

Example:

    MULTIDESK_FPS=8 MULTIDESK_JPEG_QUALITY=70 python host.py

## Troubleshooting

- **Requires X11:** log out, choose the Cinnamon on Xorg/X11 session at the login screen, then log in again.
- **Cannot open display:** start the server from a terminal inside the logged-in desktop session. Do not use sudo.
- **Cannot create MPX devices:** confirm xinput list --short works and the X server supports XInput2 master devices.
- **Guest can connect but sees no screen:** approve the guest in the host dashboard and check that the host desktop is unlocked and visible.
- **Some apps ignore a guest pointer:** the app may not support multiple XInput master devices. This is an X11 application compatibility limitation, not a browser cursor issue.

## Roadmap

- WebRTC video and an SFU for lower-latency, more bandwidth-efficient multi-viewer streaming.
- Per-guest permissions, host-side activity controls and configurable access timeouts.
- Better multi-monitor selection and display scaling.
- More automated compatibility tests across GTK, Qt, Electron and common desktop applications.
