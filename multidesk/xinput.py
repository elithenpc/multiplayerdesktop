"""Per-guest XInput master-device management and event injection for X11 MPX."""
from __future__ import annotations

import ctypes
import ctypes.util
import re
import subprocess
import threading
from dataclasses import dataclass


class XDeviceStruct(ctypes.Structure):
    _fields_ = [
        ("device_id", ctypes.c_ulong),
        ("num_classes", ctypes.c_int),
        ("classes", ctypes.c_void_p),
    ]


class XcursorImage(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint),
        ("size", ctypes.c_uint),
        ("width", ctypes.c_uint),
        ("height", ctypes.c_uint),
        ("xhot", ctypes.c_uint),
        ("yhot", ctypes.c_uint),
        ("pixels", ctypes.POINTER(ctypes.c_uint)),
        ("comment", ctypes.c_char_p),
    ]


@dataclass
class DevicePair:
    name: str
    pointer_id: int
    keyboard_id: int
    pointer: ctypes.POINTER(XDeviceStruct)
    keyboard: ctypes.POINTER(XDeviceStruct)
    cursor_id: int = 0


class XInputMPX:
    """Create one real X11 master pointer/keyboard pair for each remote guest."""

    def __init__(self) -> None:
        if not __import__("os").environ.get("DISPLAY"):
            raise RuntimeError("DISPLAY is not set. Start MultiDesk inside your logged-in X11 desktop session.")
        x11_name = ctypes.util.find_library("X11")
        xi_name = ctypes.util.find_library("Xi")
        xtst_name = ctypes.util.find_library("Xtst")
        xcursor_name = ctypes.util.find_library("Xcursor")
        if not all((x11_name, xi_name, xtst_name, xcursor_name)):
            raise RuntimeError("Missing X11 cursor libraries. Install libx11-6, libxi6, libxtst6 and libxcursor1.")
        self.x11 = ctypes.CDLL(x11_name)
        self.xi = ctypes.CDLL(xi_name)
        self.xtst = ctypes.CDLL(xtst_name)
        self.xcursor = ctypes.CDLL(xcursor_name)
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
        self.x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        self.x11.XDefaultRootWindow.restype = ctypes.c_ulong
        self.x11.XFreeCursor.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x11.XFreeCursor.restype = ctypes.c_int
        self.xi.XIChangeCursor.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong]
        self.xi.XIChangeCursor.restype = ctypes.c_int
        self.xcursor.XcursorImageCreate.argtypes = [ctypes.c_uint, ctypes.c_uint]
        self.xcursor.XcursorImageCreate.restype = ctypes.POINTER(XcursorImage)
        self.xcursor.XcursorImageDestroy.argtypes = [ctypes.POINTER(XcursorImage)]
        self.xcursor.XcursorImageLoadCursor.argtypes = [ctypes.c_void_p, ctypes.POINTER(XcursorImage)]
        self.xcursor.XcursorImageLoadCursor.restype = ctypes.c_ulong
        self.x11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.x11.XSync.restype = ctypes.c_int
        self.x11.XFlush.argtypes = [ctypes.c_void_p]
        self.x11.XFlush.restype = ctypes.c_int
        self.x11.XStringToKeysym.argtypes = [ctypes.c_char_p]
        self.x11.XStringToKeysym.restype = ctypes.c_ulong
        self.x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.x11.XKeysymToKeycode.restype = ctypes.c_uint
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
            ctypes.POINTER(ctypes.c_int), ctypes.c_int, ctypes.c_ulong
        ]
        self.xtst.XTestFakeDeviceKeyEvent.restype = ctypes.c_int

    @staticmethod
    def _run_xinput(*args: str) -> str:
        result = subprocess.run(
            ["xinput", *args], check=True, text=True, capture_output=True, timeout=5
        )
        return result.stdout

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
                # XTestFakeDevice* only reads the device_id field from
                # XDevice. Build lightweight handles for the XTEST slave IDs
                # instead of opening devices, which avoids leaving open-device
                # references behind when Xorg destroys a guest's master pair.
                pointer = ctypes.pointer(XDeviceStruct(pointer_test_id, 0, None))
                keyboard = ctypes.pointer(XDeviceStruct(keyboard_test_id, 0, None))
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
                raise

    def set_cursor_name(self, pair: DevicePair, name: str) -> None:
        """Attach a name tag to the MPX pointer's cursor, without an overlay window."""
        from PIL import Image, ImageDraw, ImageFont

        label = (str(name).strip() or "Guest")[:24]
        font = ImageFont.load_default()
        probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        bounds = ImageDraw.Draw(probe).textbbox((0, 0), label, font=font)
        width = min(220, max(100, bounds[2] - bounds[0] + 34))
        height = 34
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.polygon([(1, 1), (1, 18), (6, 13), (10, 21), (14, 19), (10, 11), (17, 11)],
                     fill=(255, 255, 255, 255), outline=(15, 23, 42, 255))
        draw.rounded_rectangle((20, 3, width - 2, 27), radius=5, fill=(15, 23, 42, 235))
        draw.text((26, 8), label, font=font, fill=(255, 255, 255, 255))

        pixels = (ctypes.c_uint * (width * height))()
        for index, (red, green, blue, alpha) in enumerate(image.getdata()):
            pixels[index] = (alpha << 24) | (red << 16) | (green << 8) | blue

        with self.lock:
            cursor_image = self.xcursor.XcursorImageCreate(width, height)
            if not cursor_image:
                raise RuntimeError("Xcursor could not allocate a named cursor.")
            try:
                cursor_image.contents.size = ctypes.sizeof(XcursorImage)
                cursor_image.contents.xhot = 1
                cursor_image.contents.yhot = 1
                ctypes.memmove(cursor_image.contents.pixels, pixels, ctypes.sizeof(pixels))
                cursor_id = self.xcursor.XcursorImageLoadCursor(self.display, cursor_image)
            finally:
                self.xcursor.XcursorImageDestroy(cursor_image)
            if not cursor_id:
                raise RuntimeError("Xcursor could not create the named cursor.")
            root = self.x11.XDefaultRootWindow(self.display)
            status = self.xi.XIChangeCursor(self.display, pair.pointer_id, root, cursor_id)
            self.x11.XFlush(self.display)
            if status != 0:
                self.x11.XFreeCursor(self.display, cursor_id)
                raise RuntimeError("XInput could not assign the named cursor to this guest pointer.")
            old_cursor = pair.cursor_id
            pair.cursor_id = cursor_id
            if old_cursor:
                self.x11.XFreeCursor(self.display, old_cursor)

    def remove_pair(self, pair: DevicePair) -> None:
        with self.lock:
            if pair.cursor_id:
                root = self.x11.XDefaultRootWindow(self.display)
                self.xi.XIChangeCursor(self.display, pair.pointer_id, root, 0)
                self.x11.XFreeCursor(self.display, pair.cursor_id)
                pair.cursor_id = 0
                self.x11.XFlush(self.display)
            # Xorg removes the XTEST slave devices together with their master pair.
            try:
                self._run_xinput(
                    "remove-master", str(pair.pointer_id), "AttachToMaster", "2", "3"
                )
            except subprocess.CalledProcessError:
                pass
            self.x11.XSync(self.display, 0)

    def move(self, pair: DevicePair, x: int, y: int) -> None:
        with self.lock:
            axes = (ctypes.c_int * 2)(int(x), int(y))
            ok = self.xtst.XTestFakeDeviceMotionEvent(
                self.display, pair.pointer, 0, 0, axes, 2, 0
            )
            self.x11.XFlush(self.display)
            if not ok:
                raise RuntimeError("XTest could not inject motion for this MPX pointer.")

    def button(self, pair: DevicePair, button: int, down: bool) -> None:
        with self.lock:
            ok = self.xtst.XTestFakeDeviceButtonEvent(
                self.display, pair.pointer, int(button), int(bool(down)), ctypes.POINTER(ctypes.c_int)(), 0, 0
            )
            self.x11.XFlush(self.display)
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
                self.display, pair.keyboard, int(code), int(bool(down)), ctypes.POINTER(ctypes.c_int)(), 0, 0
            )
            self.x11.XFlush(self.display)
            if not ok:
                raise RuntimeError("XTest could not inject a key event for this MPX keyboard.")

    def close(self) -> None:
        if self.display:
            self.x11.XCloseDisplay(self.display)
            self.display = None
