from __future__ import annotations

import logging
import warnings
from typing import Optional

import typer

from .audio.volume import detect_backend, get_volume_percent, mute, set_volume_percent
from .camera.v4l2 import capture_frame, device_exists
from .config import load_settings
from .memory.cleanup import cleanup_events
from .memory.store import MemoryStore
from .router import Router
from .skills.base import SkillContext
from .skills.registry import SkillRegistry
from .state import JoeState
from .utils.logging import configure_logging
from .voice.daemon import VoiceLoop

log = logging.getLogger(__name__)

app = typer.Typer(add_completion=False)


def _build_runtime():
    settings = load_settings()
    configure_logging(log_dir=settings.data_dir / "logs")

    memory = MemoryStore(str(settings.db_path))
    memory.init()

    state = JoeState()
    registry = SkillRegistry.build_default(
        ssd_mount=settings.hardware.storage.ssd_mount,
    )
    router = Router(registry)

    return settings, memory, state, registry, router


def _fmt_uptime_hm(uptime_s: int) -> str:
    h = uptime_s // 3600
    m = (uptime_s % 3600) // 60
    return f"{h}h{m:02d}m"


def _format_cli(res) -> str:
    """Prefer machine-readable res.data for CLI output, fallback to res.text."""
    data = getattr(res, "data", None) or {}
    if {"host", "load1", "ram_percent", "disk_percent"} <= set(data.keys()):
        host = data.get("host", "unknown")
        load1 = float(data.get("load1", 0.0))
        ram = float(data.get("ram_percent", 0.0))
        disk = float(data.get("disk_percent", 0.0))
        uptime_s = int(data.get("uptime_s", 0))
        temp = data.get("temp_c", None)
        ip = data.get("ip", None)

        msg = (
            f"{host}: CPU load {load1:.2f}, RAM {ram:.0f}%, disk {disk:.0f}%, "
            f"uptime {_fmt_uptime_hm(uptime_s)}"
        )
        if temp is not None:
            try:
                msg += f", temp {float(temp):.1f}°C"
            except Exception:
                pass
        if ip:
            msg += f", IP {ip}"
        return msg

    return getattr(res, "text", str(res))


@app.command()
def status():
    """Show system + Joe status."""
    settings, _memory, state, _registry, _router = _build_runtime()

    typer.echo(f"DB: {settings.db_path}")
    typer.echo(f"Hardware: {settings.hardware_path}")
    typer.echo(f"State: {state.snapshot()}")
    typer.echo(f"Volume backend: {detect_backend().kind}")
    v = get_volume_percent()
    typer.echo(f"Volume: {v if v is not None else 'n/a'}%")

    cam = settings.hardware.camera
    if cam.enabled:
        typer.echo(f"Camera: {cam.device} ({'present' if device_exists(cam.device) else 'absent — no-camera mode'})")
    else:
        typer.echo("Camera: disabled")

    stor = settings.hardware.storage
    typer.echo(f"Storage: root={stor.root_device}  SSD={stor.ssd_mount}")


@app.command()
def ask(text: str):
    """Route text through skills (CLI source)."""
    settings, memory, state, _registry, router = _build_runtime()
    ctx = SkillContext(source="cli", state=state, memory=memory)
    res = router.handle_text(text, ctx)
    typer.echo(_format_cli(res))


@app.command("run-voice")
def run_voice():
    """Run the MS4 demo voice loop (wake → converse)."""
    # Keep demo console output clean on RPi (CPU-only expected).
    warnings.filterwarnings(
        "ignore",
        message="Specified provider 'CUDAExecutionProvider' is not in available provider names.*",
    )
    warnings.filterwarnings(
        "ignore",
        message=".*GPU device discovery failed.*",
    )

    settings, _memory, _state, _registry, _router = _build_runtime()
    loop = VoiceLoop(settings)
    st = loop.run_forever()
    if not st.ok:
        typer.echo(f"ERROR: {st.msg}")
        raise typer.Exit(code=1)


@app.command("camera-test")
def camera_test():
    """Capture a single frame from the configured camera (or report gracefully if absent)."""
    settings, _memory, _state, _registry, _router = _build_runtime()

    cam = settings.hardware.camera
    if not cam.enabled:
        typer.echo("Camera is disabled in hardware.yaml")
        raise typer.Exit(code=0)

    r = capture_frame(cam.device, settings.data_dir / "camera")
    if r.ok:
        typer.echo(f"OK: {r.frame_path}")
    else:
        typer.echo(f"Camera not available: {r.error}")
        typer.echo("MS4 note: camera hardware may be absent — ribbon replacement ordered.")
        raise typer.Exit(code=1)


mem = typer.Typer()
app.add_typer(mem, name="memory")


@mem.command("list")
def mem_list(last: int = 20):
    settings, memory, _state, _registry, _router = _build_runtime()
    for e in memory.list_events(limit=last):
        typer.echo(f"{e['id']} {e['ts_utc']} [{e['source']}] {e['text']} ({e['intent']})")


@mem.command("facts")
def mem_facts(subject: Optional[str] = None, limit: int = 50):
    settings, memory, _state, _registry, _router = _build_runtime()
    for f in memory.list_facts(subject=subject, limit=limit):
        typer.echo(f"{f['ts_utc']} {f['subject']}.{f['predicate']} = {f['object']} (src={f['source']})")


@mem.command("clear")
def mem_clear(scope: str = typer.Option("all", help="events|facts|all")):
    settings, memory, _state, _registry, _router = _build_runtime()
    if scope in ("events", "all"):
        n = memory.clear_events()
        typer.echo(f"Cleared events: {n}")
    if scope in ("facts", "all"):
        n = memory.clear_facts()
        typer.echo(f"Cleared facts: {n}")


@mem.command("cleanup")
def mem_cleanup(ttl_days: int = 30, max_events: int = 50_000):
    settings, memory, _state, _registry, _router = _build_runtime()
    r = cleanup_events(memory, ttl_days=ttl_days, max_events=max_events)
    typer.echo(f"Cleanup: {r}")


volume = typer.Typer()
app.add_typer(volume, name="volume")


@volume.command("get")
def volume_get():
    v = get_volume_percent()
    typer.echo(f"{v if v is not None else 'n/a'}% (backend={detect_backend().kind})")


@volume.command("set")
def volume_set(value: int):
    ok = set_volume_percent(value)
    typer.echo("OK" if ok else "FAIL")


@volume.command("mute")
def volume_mute(on: bool = True):
    ok = mute(on)
    typer.echo("OK" if ok else "FAIL")


mode = typer.Typer()
app.add_typer(mode, name="mode")


@mode.command("sleep")
def mode_sleep():
    settings, memory, state, _registry, _router = _build_runtime()
    state.set_awake(False)
    typer.echo("Sleep mode ON")


@mode.command("wake")
def mode_wake():
    settings, memory, state, _registry, _router = _build_runtime()
    state.set_awake(True)
    typer.echo("Awake mode ON")
