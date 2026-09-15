"""앱 팩토리. uvicorn --factory app.main:create_app"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import sqlalchemy.exc
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.db import make_engine, make_session_factory
from app.domain.router import router as domain_router
from app.domain.topology import DomainTopology, record_provider
from app.lora_service import api
from app.lora_service.hub import Hub
from app.lora_service.router import router as lora_router
from app.settings import Settings

log = logging.getLogger("main")
SWEEP_INTERVAL_S = 5.0


def create_app(db_path: str | None = None) -> FastAPI:
    settings = Settings() if db_path is None else replace(Settings(), db_path=db_path)
    engine = make_engine(settings.db_path)
    Session = make_session_factory(engine)
    hub = Hub(Session, settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        api.configure(Session)
        api.reset_connections()
        api.set_hub(hub)
        api.set_topology(DomainTopology(Session))
        api.set_record_provider(record_provider(Session))
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
    app.include_router(domain_router)
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).resolve().parents[1] / "static"),
        name="static",
    )

    @app.exception_handler(api.NotFound)
    async def _nf(_r: Request, e: api.NotFound):
        return JSONResponse({"detail": str(e)}, status_code=404)

    @app.exception_handler(ValueError)
    async def _bad(_r: Request, e: ValueError):
        return JSONResponse({"detail": str(e)}, status_code=400)

    @app.exception_handler(sqlalchemy.exc.IntegrityError)
    async def _conflict(_r: Request, e: sqlalchemy.exc.IntegrityError):
        log.warning("IntegrityError: %s", e)
        return JSONResponse({"detail": "constraint violation"}, status_code=409)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app
