# MultiDesk

MultiDesk is the project for a browser-based collaborative desktop hosted by a Linux X11 computer.

## Current repository status

The repository now contains the initial project scaffold:

- Python host entry point using Flask-SocketIO
- Browser guest page
- Host dashboard placeholder
- Linux Mint installer and Python dependency list

**This is not yet a working remote desktop.** Screen capture, host approval workflow, remote keyboard/mouse input, true independent cursors and internet transport are not implemented in this scaffold. Do not expose the current host service to an untrusted network.

## Required end goal

- One Linux Mint X11 computer shares its actual desktop.
- Windows, Linux and macOS users connect from a browser.
- Every guest sees the same live screen.
- Every guest has a genuinely independent cursor and can click, type and scroll concurrently.
- The host approves each connection.
- Local Wi-Fi/Ethernet and remote connections through Tailscale or secured internet access.
- No arbitrary software participant cap; capacity is limited by hardware and network resources.

## Technical milestones

1. Implement screen capture and multi-viewer video delivery.
2. Implement per-guest XInput2 MPX master pointer and keyboard devices. Browser cursor overlays alone do not count as independent desktop cursors.
3. Route mouse and keyboard events to each guest's own XInput2 devices.
4. Add host approval, revocation, authentication and audit logging.
5. Add secure remote connectivity, HTTPS, rate limiting and reconnection handling.
6. Test simultaneous multi-user interactions on Linux Mint Cinnamon X11.

## Development environment

Target host: Linux Mint Cinnamon on X11. Python 3.10+.

Install the initial dependencies:

    git clone https://github.com/elithenpc/multiplayerdesktop.git
    cd multiplayerdesktop
    chmod +x install.sh
    ./install.sh

The current host entry point is only a scaffold. Do not use it for remote control yet.
