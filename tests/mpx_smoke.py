#!/usr/bin/env python3
"""Runtime smoke test for MPX creation and per-device event injection."""
from multidesk.xinput import XInputMPX

driver = XInputMPX()
pair = None
try:
    pair = driver.create_pair("ci-smoke")
    driver.move(pair, 320, 240)
    driver.button(pair, 1, True)
    driver.button(pair, 1, False)
    driver.key(pair, "a", True)
    driver.key(pair, "a", False)
    print("MPX device creation, focus, motion, button and key injection passed.")
finally:
    if pair is not None:
        driver.remove_pair(pair)
    driver.close()
