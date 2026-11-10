"""FastAPI application. Run with: uvicorn connectly.api.main:app --reload"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine, text

from connectly import __version__
from connectly.api.routers import geography, registry
from connectly.core.config import get_settings
from connectly.core.db import get_engine, make_sessionmaker


def create_app(engine: Engine | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Connectly Intelligence API",
        version=__version__,
        description="Community intelligence for technology access. Every value carries "
        "its source; missing data is reported, never invented.",
    )
    engine = engine or get_engine()
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        with engine.connect() as conn:
            postgis = conn.execute(text("SELECT postgis_lib_version()")).scalar_one()
            migration = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return {"status": "ok", "postgis": postgis, "migration": migration}

    app.include_router(geography.router)
    app.include_router(registry.router)
    return app


app = create_app()
