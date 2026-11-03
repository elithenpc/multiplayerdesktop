#!/usr/bin/env python3
"""MultiDesk: approved multi-user X11 desktop sharing using XInput2 MPX."""
from __future__ import annotations

import os
import secrets
import socket
import subprocess
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO, join_room
from multidesk.video import WebRTCManager

from multidesk.xinput import DevicePair, XInputMPX

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
CONFIG = Path.home() / ".config" / "multidesk"
CONFIG.mkdir(parents=True, exist_ok=True)
TOKEN_FILE = CONFIG / "admin.token"
if not TOKEN_FILE.exists():
    TOKEN_FILE.write_text(secrets.token_urlsafe(36) + "\n")
    TOKEN_FILE.chmod(0o600)
ADMIN_TOKEN = TOKEN_FILE.read_text().strip()

HOST = os.environ.get("MULTIDESK_HOST", "0.0.0.0")
PORT = int(os.environ.get("MULTIDESK_PORT", "8765"))
STUN_URL = os.environ.get("MULTIDESK_STUN_URL", "stun:stun.l.google.com:19302")
TURN_URLS = [u.strip() for u in os.environ.get("MULTIDESK_TURN_URL", "").split(",") if u.strip()]
TURN_USERNAME = os.environ.get("MULTIDESK_TURN_USERNAME", "")
TURN_PASSWORD = os.environ.get("MULTIDESK_TURN_PASSWORD", "")

app = Flask(__name__, static_folder=None)
app.config["SECRET_KEY"] = secrets.token_urlsafe(32)
socketio = SocketIO(
    app,
    cors_allowed_origins=None,
    async_mode="threading",
    max_http_buffer_size=1_000_000,
    ping_interval=20,
    ping_timeout=30,
)

xinput = XInputMPX()
clients: dict[str, dict] = {}
approved: dict[str, DevicePair] = {}
last_input: dict[tuple[str, str], float] = {}
state_lock = threading.RLock()
screen_size = {"width": 0, "height": 0}


def update_screen_size(width: int, height: int):
    screen_size["width"], screen_size["height"] = width, height
    socketio.emit("screen_info", screen_size)


def emit_to_guest(event: str, data: dict, sid: str):
    socketio.emit(event, data, to=sid)


video = WebRTCManager(update_screen_size, emit_to_guest)


def host_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def tailscale_ip() -> str | None:
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=2
        )
        value = result.stdout.strip().splitlines()
        return value[0] if result.returncode == 0 and value else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def admin_ok() -> bool:
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return bool(supplied) and secrets.compare_digest(supplied, ADMIN_TOKEN)


def pair_for(sid: str) -> DevicePair | None:
    with state_lock:
        return approved.get(sid)


def input_allowed(sid: str, event_type: str) -> DevicePair | None:
    now = time.monotonic()
    with state_lock:
        pair = approved.get(sid)
        key = (sid, event_type)
        previous = last_input.get(key, 0.0)
        minimum_interval = 0.0015 if event_type == "pointer" else 0.0002
        if pair is None or now - previous < minimum_interval:
            return None
        last_input[key] = now
        return pair


@app.get("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.get("/admin")
def admin():
    return send_from_directory(WEB, "admin.html")


@app.get("/api/status")
def status():
    with state_lock:
        return jsonify(
            connected=len(clients),
            approved=len(approved),
            screen=screen_size,
            video="WebRTC",
        )


@app.get("/api/webrtc-config")
def webrtc_config():
    ice_servers = [{"urls": [STUN_URL]}] if STUN_URL else []
    if TURN_URLS and TURN_USERNAME and TURN_PASSWORD:
        ice_servers.append({"urls": TURN_URLS, "username": TURN_USERNAME, "credential": TURN_PASSWORD})
    return jsonify(iceServers=ice_servers)


@app.get("/api/clients")
def list_clients():
    if not admin_ok():
        return jsonify(error="Unauthorised"), 401
    with state_lock:
        return jsonify([
            {
                "id": sid,
                "name": data["name"],
                "approved": sid in approved,
                "connected_at": data["connected_at"],
            }
            for sid, data in clients.items()
        ])


@app.post("/api/clients/<sid>/<action>")
def client_action(sid: str, action: str):
    if not admin_ok():
        return jsonify(error="Unauthorised"), 401
    if action not in {"approve", "reject", "revoke", "kick"}:
        return jsonify(error="Unknown action"), 400

    with state_lock:
        if sid not in clients:
            return jsonify(error="Guest is no longer connected"), 404
        existing = approved.get(sid)

    if action == "approve":
        if existing:
            return jsonify(ok=True, message="Already approved")
        try:
            pair = xinput.create_pair(sid)
        except Exception as exc:
            app.logger.exception("Could not create MPX devices for %s", sid)
            return jsonify(error=f"Could not create independent X11 devices: {exc}"), 500
        with state_lock:
            if sid not in clients:
                disconnected = True
                guest_name = ""
            else:
                disconnected = False
                approved[sid] = pair
                guest_name = clients[sid]["name"]
        if disconnected:
            xinput.remove_pair(pair)
            return jsonify(error="Guest disconnected during approval"), 409
        socketio.emit("access_granted", {"name": guest_name}, to=sid)
        socketio.emit("approval_changed", {"id": sid, "approved": True})
        return jsonify(ok=True, message="Approved with an independent X11 pointer and keyboard")

    if existing:
        with state_lock:
            approved.pop(sid, None)
        video.close(sid)
        xinput.remove_pair(existing)
    socketio.emit("access_denied", {"reason": "The host revoked or denied access"}, to=sid)
    socketio.emit("approval_changed", {"id": sid, "approved": False})
    if action == "kick":
        socketio.server.disconnect(sid, namespace="/")
    return jsonify(ok=True)


@socketio.on("connect")
def on_connect():
    sid = request.sid
    join_room(sid)
    with state_lock:
        clients[sid] = {"name": "Connecting", "connected_at": int(time.time())}
    socketio.emit("server_status", {"approval_required": True}, to=sid)
    socketio.emit("client_list_changed")


@socketio.on("join_request")
def join_request(data):
    name = str((data or {}).get("name", "Guest")).strip()[:32] or "Guest"
    with state_lock:
        if request.sid not in clients:
            return
        clients[request.sid]["name"] = name
    socketio.emit("join_pending", {"name": name}, to=request.sid)
    socketio.emit("client_pending", {"id": request.sid, "name": name})
    socketio.emit("client_list_changed")


@socketio.on("webrtc_offer")
def webrtc_offer(data):
    sid = request.sid
    if pair_for(sid) is None:
        socketio.emit("webrtc_error", {"message": "Host approval is required before video starts."}, to=sid)
        return
    try:
        description = {"sdp": str((data or {}).get("sdp", "")), "type": str((data or {}).get("type", ""))}
        if not description["sdp"] or description["type"] != "offer":
            raise ValueError("Invalid WebRTC offer")
        video.offer(sid, description)
    except Exception as exc:
        app.logger.exception("WebRTC setup failed for %s", sid)
        socketio.emit("webrtc_error", {"message": f"Could not start video: {exc}"}, to=sid)


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    with state_lock:
        clients.pop(sid, None)
        pair = approved.pop(sid, None)
        for key in [key for key in last_input if key[0] == sid]:
            last_input.pop(key, None)
    video.close(sid)
    if pair:
        try:
            xinput.remove_pair(pair)
        except Exception:
            app.logger.exception("Could not clean up MPX devices for %s", sid)
    socketio.emit("cursor_remove", {"id": sid})
    socketio.emit("client_list_changed")


@socketio.on("pointer")
def pointer(data):
    pair = input_allowed(request.sid, "pointer")
    if pair is None:
        return
    try:
        x = max(0.0, min(1.0, float(data.get("x", 0))))
        y = max(0.0, min(1.0, float(data.get("y", 0))))
        width = screen_size["width"]
        height = screen_size["height"]
        if not width or not height:
            return
        px = min(width - 1, round(x * (width - 1)))
        py = min(height - 1, round(y * (height - 1)))
        xinput.move(pair, px, py)
        with state_lock:
            name = clients.get(request.sid, {}).get("name", "Guest")
            recipients = list(approved.keys())
        cursor = {"id": request.sid, "name": name, "x": x, "y": y}
        for sid in recipients:
            socketio.emit("guest_cursor", cursor, to=sid)
    except (ValueError, TypeError):
        return
    except Exception:
        app.logger.exception("Pointer injection failed for %s", request.sid)


@socketio.on("mouse")
def mouse(data):
    pair = input_allowed(request.sid, "mouse")
    if pair is None:
        return
    try:
        button = int(data.get("button", 1))
        if button not in {1, 2, 3}:
            return
        xinput.button(pair, button, bool(data.get("down")))
    except (ValueError, TypeError):
        return
    except Exception:
        app.logger.exception("Mouse injection failed for %s", request.sid)


@socketio.on("wheel")
def wheel(data):
    pair = input_allowed(request.sid, "wheel")
    if pair is None:
        return
    try:
        button = 4 if float(data.get("delta", 0)) < 0 else 5
        xinput.button(pair, button, True)
        xinput.button(pair, button, False)
    except (ValueError, TypeError):
        return
    except Exception:
        app.logger.exception("Scroll injection failed for %s", request.sid)


KEY_MAP = {
    "Enter": "Return", "NumpadEnter": "KP_Enter",
    "Escape": "Escape", "Backspace": "BackSpace", "Tab": "Tab",
    "Space": "space", "Delete": "Delete", "Insert": "Insert",
    "Home": "Home", "End": "End", "PageUp": "Page_Up", "PageDown": "Page_Down",
    "ArrowUp": "Up", "ArrowDown": "Down", "ArrowLeft": "Left", "ArrowRight": "Right",
    "ShiftLeft": "Shift_L", "ShiftRight": "Shift_R",
    "ControlLeft": "Control_L", "ControlRight": "Control_R",
    "AltLeft": "Alt_L", "AltRight": "Alt_R",
    "MetaLeft": "Super_L", "MetaRight": "Super_R",
    "CapsLock": "Caps_Lock", "ContextMenu": "Menu",
    "F1": "F1", "F2": "F2", "F3": "F3", "F4": "F4", "F5": "F5", "F6": "F6",
    "F7": "F7", "F8": "F8", "F9": "F9", "F10": "F10", "F11": "F11", "F12": "F12",
    "Minus": "minus", "Equal": "equal", "BracketLeft": "bracketleft",
    "BracketRight": "bracketright", "Backslash": "backslash", "Semicolon": "semicolon",
    "Quote": "apostrophe", "Backquote": "grave", "Comma": "comma",
    "Period": "period", "Slash": "slash",
}
for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    KEY_MAP["Key" + letter] = letter.lower()
for digit in "0123456789":
    KEY_MAP["Digit" + digit] = digit
for digit in "0123456789":
    KEY_MAP["Numpad" + digit] = "KP_" + digit


@socketio.on("key")
def key(data):
    pair = input_allowed(request.sid, "key")
    if pair is None:
        return
    code = str(data.get("code", ""))[:24]
    keysym = KEY_MAP.get(code)
    if not keysym:
        return
    try:
        xinput.key(pair, keysym, bool(data.get("down")))
    except Exception:
        app.logger.exception("Keyboard injection failed for %s", request.sid)


if __name__ == "__main__":
    # Fail early if this X server cannot create independent master devices.
    try:
        probe_pair = xinput.create_pair("startup-check")
        xinput.remove_pair(probe_pair)
    except Exception as exc:
        raise SystemExit(
            "MultiDesk MPX self-test failed. Confirm this is an X11/Xorg session "
            "and that xinput can create master devices. Details: " + str(exc)
        ) from exc

    print()
    print("MultiDesk host is starting.")
    print("XInput2 MPX self-test passed.")
    print("Video transport: WebRTC (VP8).")
    print(f"Guest URL: http://{host_ip()}:{PORT}")
    tail_ip = tailscale_ip()
    if tail_ip:
        print(f"Tailscale guest URL: http://{tail_ip}:{PORT}")
    print(f"Host dashboard: http://127.0.0.1:{PORT}/admin")
    print(f"Admin token: {ADMIN_TOKEN}")
    print("Each approved guest receives a separate XInput2 MPX pointer and keyboard.")
    print("Keep the admin token private. Press Ctrl+C to stop.")
    print()
    try:
        socketio.run(app, host=HOST, port=PORT, allow_unsafe_werkzeug=True)
    finally:
        video.shutdown()
        with state_lock:
            pairs = list(approved.values())
            approved.clear()
        for pair in pairs:
            try:
                xinput.remove_pair(pair)
            except Exception:
                pass
        xinput.close()
