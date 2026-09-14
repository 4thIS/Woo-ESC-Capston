"""앱 팩토리. uvicorn --factory app.main:create_app"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace

from fastapi import FastAPI

from app.db import make_engine, make_session_factory
from app.lora_service import api
from app.lora_service.hub import Hub
from app.lora_service.router import router as lora_router
from app.settings import Settings

SWEEP_INTERVAL_S = 5.0


def create_app(db_path: str | None = None) -> FastAPI:
    settings = Settings() if db_path is None else replace(Settings(), db_path=db_path)
    engine = make_engine(settings.db_path)
    Session = make_session_factory(engine)
    hub = Hub(Session, settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        api.configure(Session)
        api.set_hub(hub)
        hub.start(asyncio.get_running_loop())
        sweeper = asyncio.ensure_future(hub.sweep_loop(SWEEP_INTERVAL_S))
        try:
            yield
        finally:
            sweeper.cancel()
            await hub.stop()

    app = FastAPI(title="Woo-ESC-Capston 메인Pi", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.Session = Session
    app.state.hub = hub
    app.include_router(lora_router)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app
