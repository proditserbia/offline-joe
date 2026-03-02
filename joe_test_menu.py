#!/usr/bin/env python3
"""Offline Joe — MS4 diagnostic menu.

Run with:
  python joe_test_menu.py

Menu items are kept intentionally thin; heavy lifting lives in:
  joe/diagnostics/deps.py     — dependency checks
  joe/diagnostics/audio.py    — audio subsystem probes
  joe/diagnostics/storage.py  — disk / SSD usage
  joe/camera/v4l2.py          — camera probe + frame capture
  joe/voice/daemon.py         — VoiceLoop (full conversation loop)
"""

from __future__ import annotations

import sys


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hr(char: str = "-", width: int = 50) -> None:
    print(char * width)


def _show_status(settings) -> None:
    from joe.audio.volume import detect_backend, get_volume_percent
    from joe.camera.v4l2 import device_exists, probe_camera

    _hr("=")
    print("  Offline Joe — System Status")
    _hr("=")
    print(f"  Hardware config : {settings.hardware_path}")
    print(f"  Database        : {settings.db_path}")
    print(f"  Data directory  : {settings.data_dir}")

    hw = settings.hardware
    print(f"  Wake phrase     : {hw.conversation.wake_phrase!r}")
    print(f"  Wake ack        : {hw.conversation.wake_ack!r}")
    print(f"  LLM enabled     : {hw.llm.enabled}")
    if hw.llm.enabled:
        print(f"    endpoint      : {hw.llm.base_url}  model={hw.llm.model}")

    # Audio
    _hr()
    print("  Audio")
    backend = detect_backend().kind
    vol = get_volume_percent()
    print(f"    Volume backend : {backend}")
    print(f"    Volume         : {vol if vol is not None else 'n/a'}%")
    print(f"    Input device   : {hw.audio.input_device}")
    print(f"    Output device  : {hw.audio.output_device}")

    # Camera
    _hr()
    print("  Camera")
    cam = hw.camera
    if not cam.enabled:
        print("    Status         : DISABLED (hardware.yaml camera.enabled=false)")
        print("    MS4 note       : No active /dev/video* — ribbon replacement ordered.")
    else:
        probe = probe_camera(cam.device)
        status = "PRESENT" if probe.available else "ABSENT"
        print(f"    Device         : {cam.device}  [{status}]")
        if not probe.available:
            print(f"    Detail         : {probe.detail}")
            print("    MS4 note       : No active /dev/video* — ribbon replacement ordered.")

    # Storage
    _hr()
    print("  Storage")
    stor = hw.storage
    print(f"    Root device    : {stor.root_device}")
    print(f"    SSD mount      : {stor.ssd_mount}")
    from joe.diagnostics.storage import probe_storage
    for s in probe_storage(["/", stor.ssd_mount]):
        if s.mounted:
            print(f"    {s.mount:<15} {s.used_gb:.1f} / {s.total_gb:.1f} GB  ({s.percent:.0f}% used)")
        else:
            print(f"    {s.mount:<15} not mounted")
    _hr("=")


def _show_deps() -> None:
    from joe.diagnostics.deps import run_all

    _hr("=")
    print("  Dependency Check")
    _hr("=")
    checks = run_all()
    ok = sum(1 for c in checks if c.ok)
    for c in checks:
        mark = "OK  " if c.ok else "MISS"
        print(f"  [{mark}] {c.name:<20} {c.detail}")
    _hr()
    print(f"  {ok}/{len(checks)} checks passed")
    _hr("=")


def _show_audio() -> None:
    from joe.diagnostics.audio import probe_audio, probe_alsa_devices

    _hr("=")
    print("  Audio Subsystem Probe")
    _hr("=")
    result = probe_audio()
    print(f"  Volume backend : {result.backend}")
    print(f"  Volume         : {result.volume_percent if result.volume_percent is not None else 'n/a'}%")
    print(f"  arecord        : {'ok' if result.arecord_ok else 'NOT FOUND'}")
    print(f"  aplay          : {'ok' if result.aplay_ok else 'NOT FOUND'}")
    _hr()
    print("  ALSA playback devices (aplay -l):")
    for line in probe_alsa_devices():
        print(f"    {line}")
    _hr("=")


def _show_storage(settings) -> None:
    from joe.diagnostics.storage import probe_storage

    stor = settings.hardware.storage
    mounts = ["/", stor.ssd_mount]

    _hr("=")
    print("  Storage Probe")
    _hr("=")
    print(f"  Root device : {stor.root_device}")
    for s in probe_storage(mounts):
        if s.mounted:
            bar_len = int(s.percent / 5)
            bar = "#" * bar_len + "-" * (20 - bar_len)
            print(f"  {s.mount:<15} [{bar}] {s.percent:.0f}%  {s.free_gb:.1f} GB free / {s.total_gb:.1f} GB total")
        else:
            print(f"  {s.mount:<15} NOT MOUNTED")
    _hr("=")


def _camera_test(settings) -> None:
    from joe.camera.v4l2 import capture_frame, probe_camera

    cam = settings.hardware.camera
    _hr("=")
    print("  Camera Test")
    _hr("=")
    if not cam.enabled:
        print("  Camera DISABLED in hardware.yaml")
        print("  MS4 note: no active /dev/video* device — ribbon replacement ordered.")
        _hr("=")
        return

    probe = probe_camera(cam.device)
    if not probe.available:
        print(f"  Camera ABSENT: {probe.detail}")
        print("  MS4 note: no active /dev/video* device — ribbon replacement ordered.")
        _hr("=")
        return

    result = capture_frame(cam.device, settings.data_dir / "camera")
    if result.ok:
        print(f"  Frame captured: {result.frame_path}")
    else:
        print(f"  Capture failed: {result.error}")
    _hr("=")


# ---------------------------------------------------------------------------
# Menu loop
# ---------------------------------------------------------------------------

def main() -> int:
    from joe.config import load_settings

    try:
        settings = load_settings()
    except Exception as exc:
        print(f"ERROR loading settings: {exc}", file=sys.stderr)
        return 1

    while True:
        print()
        _hr("=")
        print("  Offline Joe — MS4 Diagnostic Menu")
        _hr("=")
        print("  1) System status")
        print("  2) Dependency check")
        print("  3) Audio probe")
        print("  4) Storage probe")
        print("  5) Camera test")
        print("  6) Run voice loop  (Ctrl+C to stop)")
        print("  0) Exit")
        _hr()
        choice = (input("  > ") or "").strip()

        if choice == "0":
            return 0

        elif choice == "1":
            _show_status(settings)

        elif choice == "2":
            _show_deps()

        elif choice == "3":
            _show_audio()

        elif choice == "4":
            _show_storage(settings)

        elif choice == "5":
            _camera_test(settings)

        elif choice == "6":
            from joe.voice.daemon import VoiceLoop
            loop = VoiceLoop(settings)
            st = loop.run_forever()
            print(f"\n  Voice loop ended: {st.msg}")

        else:
            print("  Unknown option — try 0–6.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
