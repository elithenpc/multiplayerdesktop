#!/usr/bin/env python3
"""MultiDesk host service prototype."""
from pathlib import Path
from flask import Flask, send_from_directory
from flask_socketio import SocketIO

ROOT = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=None)
app.config["SECRET_KEY"] = "replace-this-with-a-random-secret"
socketio = SocketIO(app, cors_allowed_origins=[])

@app.get("/")
def index():
    return send_from_directory(ROOT / "web", "index.html")

@app.get("/admin")
def admin():
    return send_from_directory(ROOT / "web", "admin.html")

if __name__ == "__main__":
    print("MultiDesk host starting on port 8765")
    socketio.run(app, host="0.0.0.0", port=8765)
