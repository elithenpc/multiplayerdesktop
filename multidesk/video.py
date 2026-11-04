"""WebRTC desktop video capture and peer management."""
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

# A lower, fixed stream profile is much easier on laptop CPUs and tailnet links.
VIDEO_FPS = 15
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_CLOCK_RATE = 90_000


class DesktopVideoTrack(VideoStreamTrack):
    """15 fps, 720p maximum desktop track encoded by aiortc (VP8 by default)."""

    def __init__(self, on_size: Callable[[int, int], None]):
        super().__init__()
        self.capture = mss()
        self.monitor = self.capture.monitors[0]
        self._frame_index = 0
        self._last_frame_time = 0.0
        on_size(self.monitor["width"], self.monitor["height"])

    async def recv(self):
        if self.readyState != "live":
            from aiortc.mediastreams import MediaStreamError
            raise MediaStreamError

        now = time.monotonic()
        delay = (1 / VIDEO_FPS) - (now - self._last_frame_time)
        if self._last_frame_time and delay > 0:
            await asyncio.sleep(delay)
        self._last_frame_time = time.monotonic()

        shot = self.capture.grab(self.monitor)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
        image.thumbnail((VIDEO_WIDTH, VIDEO_HEIGHT), Image.Resampling.BILINEAR)
        frame = VideoFrame.from_ndarray(np.asarray(image), format="rgb24")

        self._frame_index += 1
        frame.pts = round(self._frame_index * VIDEO_CLOCK_RATE / VIDEO_FPS)
        frame.time_base = Fraction(1, VIDEO_CLOCK_RATE)
        return frame

    def stop(self):
        if getattr(self, "capture", None) is not None:
            self.capture.close()
            self.capture = None
        super().stop()


class WebRTCManager:
    """Owns aiortc peers on a dedicated asyncio event loop."""

    def __init__(self, on_size: Callable[[int, int], None], emit: Callable):
        self.on_size = on_size
        self.emit = emit
        self.peers: dict[str, tuple[RTCPeerConnection, DesktopVideoTrack]] = {}
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, name="multidesk-webrtc", daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            raise RuntimeError("WebRTC event loop did not start")

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.ready.set()
        self.loop.run_forever()

    def offer(self, sid: str, description: dict):
        future = asyncio.run_coroutine_threadsafe(self._offer(sid, description), self.loop)
        return future.result(timeout=45)

    async def _offer(self, sid: str, description: dict):
        await self._close(sid)
        pc = RTCPeerConnection()
        track = DesktopVideoTrack(self.on_size)
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
