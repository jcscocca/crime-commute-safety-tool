from __future__ import annotations

from fastapi import FastAPI

from app.api.routes_crime import router as crime_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_exports import router as exports_router
from app.api.routes_health import router as health_router
from app.api.routes_imports import router as imports_router
from app.api.routes_input_modes import router as input_modes_router
from app.api.routes_places import router as places_router
from app.db import configure_database, init_db


def create_app(database_url: str | None = None) -> FastAPI:
    configure_database(database_url)
    init_db()
    app = FastAPI(
        title="Mobility Context Analyzer",
        version="0.1.0",
        description="Privacy-first recurring-place and Seattle crime context API.",
    )
    app.include_router(health_router)
    app.include_router(imports_router)
    app.include_router(input_modes_router)
    app.include_router(places_router)
    app.include_router(crime_router)
    app.include_router(dashboard_router)
    app.include_router(exports_router)
    return app


app = create_app()
