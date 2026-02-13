#!/usr/bin/env python3
"""Offline Joe diagnostic menu (optional).

This script is intentionally dependency-light and uses the same modules as the `joe` CLI.

Usage:
  python joe_test_menu.py
"""

from __future__ import annotations

import sys

from joe.config import load_settings
from joe.audio.volume import detect_backend, get_volume_percent
from joe.camera.v4l2 import capture_frame
from joe.voice.daemon import VoiceLoop


def main() -> int:
    settings = load_settings()
    while True:
        print("\n=== Offline Joe Test Menu ===")
        print("1) Show status")
        print("2) Camera test")
        print("3) Run voice loop (Ctrl+C to stop)")
        print("0) Exit")
        choice = (input("> ") or "").strip()

        if choice == "0":
            return 0

        if choice == "1":
            print(f"Hardware: {settings.hardware_path}")
            print(f"DB: {settings.db_path}")
            print(f"Volume backend: {detect_backend().kind}")
            v = get_volume_percent()
            print(f"Volume: {v if v is not None else 'n/a'}%")
            print(f"Camera enabled: {settings.hardware.camera.enabled} ({settings.hardware.camera.device})")

        elif choice == "2":
            cam = settings.hardware.camera
            r = capture_frame(cam.device, settings.data_dir / "camera")
            if r.ok:
                print(f"OK: {r.frame_path}")
            else:
                print(f"FAIL: {r.error}")

        elif choice == "3":
            loop = VoiceLoop(settings)
            st = loop.run_forever()
            print(st.msg)

        else:
            print("Unknown option.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
