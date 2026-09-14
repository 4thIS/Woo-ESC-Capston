"""앱 팩토리. uvicorn --factory app.main:create_app"""

from __future__ import annotations

from dataclasses import replace

from fastapi import FastAPI

from app.db import make_engine, make_session_factory
from app.settings import Settings


def create_app(db_path: str | None = None) -> FastAPI:
    settings = Settings() if db_path is None else replace(Settings(), db_path=db_path)
    engine = make_engine(settings.db_path)
    app = FastAPI(title="Woo-ESC-Capston 메인Pi")
    app.state.settings = settings
    app.state.engine = engine
    app.state.Session = make_session_factory(engine)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app
