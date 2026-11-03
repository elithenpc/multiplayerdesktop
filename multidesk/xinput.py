"""Per-guest XInput master-device management and event injection for X11 MPX."""
from __future__ import annotations

import ctypes
import ctypes.util
import re
import subprocess
import threading
from dataclasses import dataclass


class XInputClassInfo(ctypes.Structure):
    _fields_ = [("input_class", ctypes.c_ubyte), ("event_type_base", ctypes.c_ubyte)]


class XDeviceStruct(ctypes.Structure):
    _fields_ = [
        ("device_id", ctypes.c_ulong),
        ("num_classes", ctypes.c_int),
        ("classes", ctypes.POINTER(XInputClassInfo)),
    ]


@dataclass
class DevicePair:
    name: str
    pointer_id: int
    keyboard_id: int
    pointer: int
    keyboard: int


class XInputMPX:
    """Create one real X11 master pointer/keyboard pair for each remote guest."""

    def __init__(self) -> None:
        if not __import__("os").environ.get("DISPLAY"):
            raise RuntimeError("DISPLAY is not set. Start MultiDesk inside your logged-in X11 desktop session.")
        x11_name = ctypes.util.find_library("X11")
        xi_name = ctypes.util.find_library("Xi")
        xtst_name = ctypes.util.find_library("Xtst")
        if not all((x11_name, xi_name, xtst_name)):
            raise RuntimeError("Missing X11 input libraries. Install libx11-6, libxi6 and libxtst6.")
        self.x11 = ctypes.CDLL(x11_name)
        self.xi = ctypes.CDLL(xi_name)
        self.xtst = ctypes.CDLL(xtst_name)
        self._configure()
        self.display = self.x11.XOpenDisplay(None)
        if not self.display:
            raise RuntimeError("Could not connect to the X display. Run the server as the logged-in desktop user, not with sudo.")
        self.lock = threading.RLock()

    def _configure(self) -> None:
        self.x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        self.x11.XOpenDisplay.restype = ctypes.c_void_p
        self.x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        self.x11.XCloseDisplay.restype = ctypes.c_int
        self.x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.x11.XSync.restype = ctypes.c_int
        self.x11.XFree.argtypes = [ctypes.c_void_p]
        self.x11.XFree.restype = ctypes.c_int
        self.x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
        self.x11.XStringToKeysym.restype = ctypes.c_ulong
        self.x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x11.XKeysymToKeycode.restype = ctypes.c_uint
        self.xi.XOpenDevice.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.xi.XOpenDevice.restype = ctypes.c_void_p
        self.xi.XCloseDevice.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.xi.XCloseDevice.restype = ctypes.c_int
        self.xi.XISetFocus.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong
        ]
        self.xi.XISetFocus.restype = ctypes.c_int
        self.xtst.XTestFakeDeviceMotionEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_ulong
        ]
        self.xtst.XTestFakeDeviceMotionEvent.restype = ctypes.c_int
        self.xtst.XTestFakeDeviceButtonEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int,
            ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_ulong
        ]
        self.xtst.XTestFakeDeviceButtonEvent.restype = ctypes.c_int
        self.xtst.XTestFakeDeviceKeyEvent.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, ctypes.c_ulong
        ]
        self.xtst.XTestFakeDeviceKeyEvent.restype = ctypes.c_int

    @staticmethod
    def _run_xinput(*args: str) -> str:
        result = subprocess.run(
            ["xinput", *args], check=True, text=True, capture_output=True, timeout=5
        )
        return result.stdout

    def _free_device_handle(self, handle: int | None) -> None:
        if not handle:
            return
        device = ctypes.cast(handle, ctypes.POINTER(XDeviceStruct)).contents
        if device.classes:
            self.x11.XFree(device.classes)
        self.x11.XFree(handle)

    def create_pair(self, guest_id: str) -> DevicePair:
        pointer = None
        keyboard = None
        safe = re.sub(r"[^A-Za-z0-9_-]", "", guest_id)[:12] or "guest"
        name = "MultiDesk-" + safe
        with self.lock:
            self._run_xinput("create-master", name, "1", "1")
            try:
                listing = self._run_xinput("list", "--short")
                pointer_match = re.search(
                    rf"{re.escape(name)} pointer\s+id=(\d+)", listing
                )
                keyboard_match = re.search(
                    rf"{re.escape(name)} keyboard\s+id=(\d+)", listing
                )
                xtest_pointer_match = re.search(
                    rf"{re.escape(name)} XTEST pointer\s+id=(\d+)", listing
                )
                xtest_keyboard_match = re.search(
                    rf"{re.escape(name)} XTEST keyboard\s+id=(\d+)", listing
                )
                if not all((pointer_match, keyboard_match, xtest_pointer_match, xtest_keyboard_match)):
                    raise RuntimeError("XInput created the master pair but its paired XTEST slave devices could not be found.")
                pointer_id = int(pointer_match.group(1))
                keyboard_id = int(keyboard_match.group(1))
                pointer_test_id = int(xtest_pointer_match.group(1))
                keyboard_test_id = int(xtest_keyboard_match.group(1))
                # XOpenDevice cannot open master devices. XTEST creates a
                # virtual slave for each master; injecting through that slave
                # routes events to its paired master device.
                pointer = self.xi.XOpenDevice(self.display, pointer_test_id)
                keyboard = self.xi.XOpenDevice(self.display, keyboard_test_id)
                if not pointer or not keyboard:
                    raise RuntimeError("XOpenDevice failed for the new MPX XTEST pointer or keyboard.")
                # PointerRoot makes this guest keyboard follow its own paired
                # master pointer, rather than the host's single keyboard focus.
                focus_status = self.xi.XISetFocus(self.display, keyboard_id, 1, 0)
                self.x11.XSync(self.display, 0)
                if focus_status != 0:
                    raise RuntimeError("Could not set the guest keyboard to its own pointer focus.")
                return DevicePair(name, pointer_id, keyboard_id, pointer, keyboard)
            except Exception:
                try:
                    self._run_xinput("remove-master", name + " pointer", "AttachToMaster", "2", "3")
                except Exception:
                    pass
                self._free_device_handle(pointer)
                self._free_device_handle(keyboard)
                raise

    def remove_pair(self, pair: DevicePair) -> None:
        with self.lock:
            # Xorg removes the XTEST slave devices with their master pair.
            # XCloseDevice can return XI_BadDevice for these auto-managed
            # XTEST devices, so free the client-side XDevice structures
            # directly after the server has removed the pair.
            try:
                self._run_xinput(
                    "remove-master", str(pair.pointer_id), "AttachToMaster", "2", "3"
                )
            except subprocess.CalledProcessError:
                pass
            self.x11.XSync(self.display, 0)
            self._free_device_handle(pair.pointer)
            self._free_device_handle(pair.keyboard)

    def move(self, pair: DevicePair, x: int, y: int) -> None:
        with self.lock:
            axes = (ctypes.c_int * 2)(int(x), int(y))
            ok = self.xtst.XTestFakeDeviceMotionEvent(
                self.display, pair.pointer, 0, 0, axes, 2, 0
            )
            self.x11.XSync(self.display, 0)
            if not ok:
                raise RuntimeError("XTest could not inject motion for this MPX pointer.")

    def button(self, pair: DevicePair, button: int, down: bool) -> None:
        with self.lock:
            ok = self.xtst.XTestFakeDeviceButtonEvent(
                self.display, pair.pointer, int(button), int(bool(down)), None, 0, 0
            )
            self.x11.XSync(self.display, 0)
            if not ok:
                raise RuntimeError("XTest could not inject a button event for this MPX pointer.")

    def key(self, pair: DevicePair, keysym_name: str, down: bool) -> None:
        sym = self.x11.XStringToKeysym(keysym_name.encode("ascii", "ignore"))
        if not sym:
            return
        code = self.x11.XKeysymToKeycode(self.display, sym)
        if not code:
            return
        with self.lock:
            ok = self.xtst.XTestFakeDeviceKeyEvent(
                self.display, pair.keyboard, int(code), int(bool(down)), None, 0, 0
            )
            self.x11.XSync(self.display, 0)
            if not ok:
                raise RuntimeError("XTest could not inject a key event for this MPX keyboard.")

    def close(self) -> None:
        if self.display:
            self.x11.XCloseDisplay(self.display)
            self.display = None
