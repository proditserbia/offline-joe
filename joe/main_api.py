from __future__ import annotations
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any

from .config import load_settings
from .memory.store import MemoryStore
from .memory.cleanup import cleanup_events
from .skills.registry import SkillRegistry
from .router import Router
from .state import JoeState
from .audio.volume import detect_backend, get_volume_percent

settings = load_settings()
memory = MemoryStore(str(settings.db_path))
memory.init()

state = JoeState()
registry = SkillRegistry.build_default()
router = Router(registry)

app = FastAPI(title="Offline Joe M4", version="0.4.0")

class RunRequest(BaseModel):
    text: str
    source: str = "api"

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/status")
def status():
    v = get_volume_percent()
    return {
        "ok": True,
        "state": state.snapshot(),
        "volume": v,
        "volume_backend": detect_backend().kind,
        "db_path": str(settings.db_path),
        "hardware_yaml": str(settings.hardware_path),
        "camera": {
            "enabled": settings.hardware.camera.enabled,
            "device": settings.hardware.camera.device,
        },
    }

@app.get("/skills")
def skills():
    return {"skills": registry.list()}

@app.post("/run")
def run_skill(req: RunRequest):
    from .skills.base import SkillContext
    ctx = SkillContext(source=req.source, state=state, memory=memory)
    res = router.handle_text(req.text, ctx)
    return {"ok": res.ok, "text": res.text, "data": res.data, "actions": res.actions}

@app.get("/memory/events")
def memory_events(limit: int = 20):
    return {"events": memory.list_events(limit=limit)}

@app.get("/memory/facts")
def memory_facts(subject: str | None = None, limit: int = 50):
    return {"facts": memory.list_facts(subject=subject, limit=limit)}

@app.post("/memory/cleanup")
def memory_cleanup():
    result = cleanup_events(memory, ttl_days=settings.events_ttl_days, max_events=settings.max_events)
    return {"ok": True, **result}
