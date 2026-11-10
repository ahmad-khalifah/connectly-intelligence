"""FastAPI application. Run with: uvicorn connectly.api.main:app --reload"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine, text

from connectly import __version__
from connectly.api.deps import current_user
from connectly.api.routers import (
    audit_log,
    auth,
    claims,
    community,
    directory,
    geography,
    matching,
    needs,
    registry,
)
from connectly.core.config import get_settings
from connectly.core.db import get_engine, make_sessionmaker
from connectly.core.security import signing_key


def create_app(engine: Engine | None = None) -> FastAPI:
    settings = get_settings()
    signing_key(settings)  # fail fast on an unsafe production configuration
    app = FastAPI(
        title="Connectly Intelligence API",
        version=__version__,
        description="Community intelligence for technology access. Every value carries "
        "its source; missing data is reported, never invented.",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    engine = engine or get_engine()
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        with engine.connect() as conn:
            postgis = conn.execute(text("SELECT postgis_lib_version()")).scalar_one()
            migration = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        return {"status": "ok", "postgis": postgis, "migration": migration}

    # Everything except /health and sign-in needs a signed-in user.
    signed_in = [Depends(current_user)]
    app.include_router(auth.router)
    app.include_router(geography.router, dependencies=signed_in)
    app.include_router(registry.router, dependencies=signed_in)
    app.include_router(community.router, dependencies=signed_in)
    app.include_router(needs.router, dependencies=signed_in)
    app.include_router(matching.router, dependencies=signed_in)
    app.include_router(claims.router)
    app.include_router(audit_log.router)
    app.include_router(directory.router)
    return app


app = create_app()
