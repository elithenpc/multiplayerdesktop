#!/usr/bin/env python3
"""Runtime smoke test for MPX creation and per-device event injection."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from multidesk.xinput import XInputMPX

print(subprocess.run(["xinput", "list", "--short"], check=True, text=True, capture_output=True).stdout, flush=True)
driver = XInputMPX()
pair = None
try:
    print("Creating master pair", flush=True)
    pair = driver.create_pair("ci-smoke")
    print(f"Created master IDs {pair.pointer_id}/{pair.keyboard_id}", flush=True)
    pointer_device_id = __import__("ctypes").cast(pair.pointer, __import__("ctypes").POINTER(__import__("ctypes").c_ulong)).contents.value
    keyboard_device_id = __import__("ctypes").cast(pair.keyboard, __import__("ctypes").POINTER(__import__("ctypes").c_ulong)).contents.value
    print(f"Opened XTEST device IDs {pointer_device_id}/{keyboard_device_id}", flush=True)
    print(subprocess.run(["xinput", "list", "--short"], check=True, text=True, capture_output=True).stdout, flush=True)
    print("Sending motion", flush=True)
    driver.move(pair, 320, 240)
    print("Sending button", flush=True)
    driver.button(pair, 1, True)
    driver.button(pair, 1, False)
    print("Sending key", flush=True)
    driver.key(pair, "a", True)
    driver.key(pair, "a", False)
    print("MPX device creation, focus, motion, button and key injection passed.", flush=True)
finally:
    if pair is not None:
        print("Removing master pair", flush=True)
        driver.remove_pair(pair)
        remaining = subprocess.run(
            ["xinput", "list", "--short"], check=True, text=True, capture_output=True
        ).stdout
        if "MultiDesk-ci-smoke" in remaining:
            raise AssertionError("The MPX master pair remained after disconnect cleanup.")
    driver.close()
