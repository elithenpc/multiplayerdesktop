"""Shared desktop capture with per-guest WebRTC video tracks."""
from __future__ import annotations

import asyncio
import threading
import time
from fractions import Fraction
from typing import Callable

import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame
from mss import mss
from PIL import Image

VIDEO_FPS = 60
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_CLOCK_RATE = 90_000
FRAME_INTERVAL = 1.0 / VIDEO_FPS
RESOLUTION_PROFILES = {
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
}


class SharedDesktopCapture:
    """Capture once and share the latest frame with all connected guests."""

    def __init__(self, on_size: Callable[[int, int], None]):
        self.on_size = on_size
        self.lock = threading.Lock()
        self.latest: np.ndarray | None = None
        self.running = True
        self.error: Exception | None = None
        self.thread = threading.Thread(target=self._capture_loop, name="multidesk-screen-capture", daemon=True)
        self.thread.start()

    def _capture_loop(self):
        try:
            with mss() as capture:
                monitor = capture.monitors[0]
                self.on_size(monitor["width"], monitor["height"])
                deadline = time.monotonic()
                while self.running:
                    shot = capture.grab(monitor)
                    image = Image.frombytes("RGB", shot.size, shot.rgb)
                    if image.width > VIDEO_WIDTH or image.height > VIDEO_HEIGHT:
                        image.thumbnail((VIDEO_WIDTH, VIDEO_HEIGHT), Image.Resampling.BILINEAR)
                    frame = np.asarray(image, dtype=np.uint8)
                    with self.lock:
                        self.latest = frame
                    deadline += FRAME_INTERVAL
                    delay = deadline - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    else:
                        deadline = time.monotonic()
        except Exception as exc:
            self.error = exc
            self.running = False

    def get_frame(self) -> np.ndarray:
        with self.lock:
            frame = self.latest
        if frame is None:
            if self.error:
                raise RuntimeError(f"Desktop capture failed: {self.error}") from self.error
            raise RuntimeError("Desktop capture is starting")
        return frame

    def close(self):
        self.running = False
        self.thread.join(timeout=3)


class DesktopVideoTrack(VideoStreamTrack):
    """60 fps video track backed by the shared desktop capture."""

    def __init__(self, capture: SharedDesktopCapture, resolution: str = "720p"):
        super().__init__()
        self.shared_capture = capture
        self.max_width, self.max_height = RESOLUTION_PROFILES.get(resolution, RESOLUTION_PROFILES["720p"])
        self.resolution = resolution
        self._frame_index = 0
        self._last_frame_time = 0.0

    async def recv(self):
        if self.readyState != "live":
            from aiortc.mediastreams import MediaStreamError
            raise MediaStreamError

        now = time.monotonic()
        delay = FRAME_INTERVAL - (now - self._last_frame_time)
        if self._last_frame_time and delay > 0:
            await asyncio.sleep(delay)
        self._last_frame_time = time.monotonic()

        image = self.shared_capture.get_frame()
        if image.shape[1] > self.max_width or image.shape[0] > self.max_height:
            resized = Image.fromarray(image)
            resized.thumbnail((self.max_width, self.max_height), Image.Resampling.BILINEAR)
            image = np.asarray(resized, dtype=np.uint8)
        frame = VideoFrame.from_ndarray(image, format="rgb24")
        self._frame_index += 1
        frame.pts = round(self._frame_index * VIDEO_CLOCK_RATE / VIDEO_FPS)
        frame.time_base = Fraction(1, VIDEO_CLOCK_RATE)
        return frame


class WebRTCManager:
    """Owns WebRTC peers on a dedicated asyncio event loop."""

    def __init__(self, on_size: Callable[[int, int], None], emit: Callable):
        self.on_size = on_size
        self.emit = emit
        self.capture = SharedDesktopCapture(on_size)
        self.peers: dict[str, tuple[RTCPeerConnection, DesktopVideoTrack]] = {}
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, name="multidesk-webrtc", daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            self.capture.close()
            raise RuntimeError("WebRTC event loop did not start")

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.ready.set()
        self.loop.run_forever()

    def offer(self, sid: str, description: dict, resolution: str = "720p"):
        if resolution not in RESOLUTION_PROFILES:
            resolution = "720p"
        future = asyncio.run_coroutine_threadsafe(self._offer(sid, description, resolution), self.loop)
        return future.result(timeout=45)

    async def _offer(self, sid: str, description: dict, resolution: str):
        await self._close(sid)
        pc = RTCPeerConnection()
        track = DesktopVideoTrack(self.capture, resolution)
        self.peers[sid] = (pc, track)
        pc.addTrack(track)

        @pc.on("connectionstatechange")
        async def connection_state_changed():
            if pc.connectionState in {"failed", "closed"}:
                await self._close(sid)

        try:
            await pc.setRemoteDescription(
                RTCSessionDescription(sdp=description["sdp"], type=description["type"])
            )
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            self.emit("webrtc_answer", {
                "sdp": pc.localDescription.sdp,
                "type": pc.localDescription.type,
            }, sid)
        except Exception:
            await self._close(sid)
            raise

    async def _close(self, sid: str):
        entry = self.peers.pop(sid, None)
        if entry:
            pc, track = entry
            track.stop()
            await pc.close()

    def close(self, sid: str):
        future = asyncio.run_coroutine_threadsafe(self._close(sid), self.loop)
        try:
            future.result(timeout=10)
        except Exception:
            pass

    async def _close_all(self):
        for sid in list(self.peers):
            await self._close(sid)

    def shutdown(self):
        future = asyncio.run_coroutine_threadsafe(self._close_all(), self.loop)
        try:
            future.result(timeout=15)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        self.capture.close()
