from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from .audio.volume import detect_backend, get_volume_percent
from .config import load_settings
from .memory.cleanup import cleanup_events
from .memory.store import MemoryStore
from .router import Router
from .skills.registry import SkillRegistry
from .state import JoeState
from .utils.logging import configure_logging

log = logging.getLogger(__name__)


class RunRequest(BaseModel):
    text: str
    source: str = "api"


def create_app() -> FastAPI:
    """FastAPI app factory (avoids side-effects at import time)."""
    settings = load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(log_dir=settings.data_dir / "logs")
        memory = MemoryStore(str(settings.db_path))
        memory.init()

        state = JoeState()
        registry = SkillRegistry.build_default()
        router = Router(registry)

        app.state.settings = settings
        app.state.memory = memory
        app.state.state = state
        app.state.registry = registry
        app.state.router = router

        log.info("Offline Joe API started. db=%s hardware=%s", settings.db_path, settings.hardware_path)
        try:
            yield
        finally:
            try:
                memory.close()
            except Exception:
                pass

    app = FastAPI(title="Offline Joe M4", version="0.4.0", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/status")
    def status():
        settings = app.state.settings
        state = app.state.state
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
        registry = app.state.registry
        return {"skills": registry.list()}

    @app.post("/run")
    def run_skill(req: RunRequest):
        from .skills.base import SkillContext

        memory = app.state.memory
        state = app.state.state
        router = app.state.router
        ctx = SkillContext(source=req.source, state=state, memory=memory)
        res = router.handle_text(req.text, ctx)
        return {"ok": res.ok, "text": res.text, "data": res.data, "actions": res.actions}

    @app.get("/memory/events")
    def memory_events(limit: int = 20):
        memory = app.state.memory
        return {"events": memory.list_events(limit=limit)}

    @app.get("/memory/facts")
    def memory_facts(subject: str | None = None, limit: int = 50):
        memory = app.state.memory
        return {"facts": memory.list_facts(subject=subject, limit=limit)}

    @app.post("/memory/cleanup")
    def memory_cleanup():
        settings = app.state.settings
        memory = app.state.memory
        result = cleanup_events(memory, ttl_days=settings.events_ttl_days, max_events=settings.max_events)
        return {"ok": True, **result}

    return app


# Uvicorn entrypoint: `uvicorn joe.main_api:app`
app = create_app()
