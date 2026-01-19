from __future__ import annotations
import typer
from typing import Optional

from .config import load_settings
from .memory.store import MemoryStore
from .memory.cleanup import cleanup_events
from .skills.registry import SkillRegistry
from .router import Router
from .state import JoeState
from .audio.volume import detect_backend, get_volume_percent, set_volume_percent, mute
from .camera.v4l2 import device_exists, capture_frame
from .voice.daemon import VoiceLoop

app = typer.Typer(add_completion=False)
settings = load_settings()
memory = MemoryStore(str(settings.db_path))
memory.init()

state = JoeState()
registry = SkillRegistry.build_default()
router = Router(registry)

def _fmt_uptime_hm(uptime_s: int) -> str:
    h = uptime_s // 3600
    m = (uptime_s % 3600) // 60
    return f"{h}h{m:02d}m"

def _format_cli(res) -> str:
    """
    Prefer machine-readable res.data for CLI output, fallback to res.text.
    """
    data = getattr(res, "data", None) or {}
    # If this looks like system_status payload, print numeric-friendly line
    if "host" in data and "load1" in data and "ram_percent" in data and "disk_percent" in data:
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

    # Default
    return getattr(res, "text", str(res))

def _ctx(source: str):
    from .skills.base import SkillContext
    return SkillContext(source=source, state=state, memory=memory)

@app.command()
def status():
    """Show system + joe status."""
    typer.echo(f"DB: {settings.db_path}")
    typer.echo(f"Hardware: {settings.hardware_path}")
    typer.echo(f"State: {state.snapshot()}")
    typer.echo(f"Volume backend: {detect_backend().kind}")
    typer.echo(f"Volume: {get_volume_percent()}%")

    cam = settings.hardware.camera
    if cam.enabled:
        typer.echo(f"Camera: {cam.device} ({'present' if device_exists(cam.device) else 'missing'})")

@app.command()
def ask(text: str):
    """Route text through skills (CLI source)."""
    res = router.handle_text(text, _ctx("cli"))
    typer.echo(_format_cli(res))


@app.command("run-voice")
def voice_run():
    """Run the MS4 demo voice loop (wake → converse)."""
    loop = VoiceLoop(settings)
    st = loop.run_forever()
    if not st.ok:
        typer.echo(f"ERROR: {st.msg}")


@app.command("camera-test")
def camera_test():
    """Initialize camera hooks and capture a single frame."""
    cam = settings.hardware.camera
    if not cam.enabled:
        typer.echo("Camera is disabled in hardware.yaml")
        raise typer.Exit(code=1)
    r = capture_frame(cam.device, settings.data_dir / "camera")
    if r.ok:
        typer.echo(f"OK: {r.frame_path}")
    else:
        typer.echo(f"FAIL: {r.error}")
        raise typer.Exit(code=1)

mem = typer.Typer()
app.add_typer(mem, name="memory")

@mem.command("list")
def mem_list(last: int = 20):
    for e in memory.list_events(limit=last):
        typer.echo(f"{e['id']} {e['ts_utc']} [{e['source']}] {e['text']} ({e['intent']})")

@mem.command("facts")
def mem_facts(subject: Optional[str] = None, limit: int = 50):
    for f in memory.list_facts(subject=subject, limit=limit):
        typer.echo(f"{f['ts_utc']} {f['subject']}.{f['predicate']} = {f['object']} (src={f['source']})")

@mem.command("clear")
def mem_clear(scope: str = typer.Option("all", help="events|facts|all")):
    if scope in ("events", "all"):
        n = memory.clear_events()
        typer.echo(f"Cleared events: {n}")
    if scope in ("facts", "all"):
        n = memory.clear_facts()
        typer.echo(f"Cleared facts: {n}")

@mem.command("cleanup")
def mem_cleanup(ttl_days: int = settings.events_ttl_days, max_events: int = settings.max_events):
    r = cleanup_events(memory, ttl_days=ttl_days, max_events=max_events)
    typer.echo(f"Cleanup: {r}")

voice = typer.Typer()
app.add_typer(voice, name="volume")

@voice.command("get")
def voice_get():
    typer.echo(f"{get_volume_percent()}% (backend={detect_backend().kind})")

@voice.command("set")
def voice_set(value: int):
    ok = set_volume_percent(value)
    typer.echo("OK" if ok else "FAIL")

@voice.command("mute")
def voice_mute(on: bool = True):
    ok = mute(on)
    typer.echo("OK" if ok else "FAIL")

mode = typer.Typer()
app.add_typer(mode, name="mode")

@mode.command("sleep")
def mode_sleep():
    state.set_awake(False)
    typer.echo("Sleep mode ON")

@mode.command("wake")
def mode_wake():
    state.set_awake(True)
    typer.echo("Awake mode ON")
