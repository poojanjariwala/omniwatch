"""OmniWatch FastAPI application."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.db import init_db

_CSP_PROD = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; media-src 'self' blob: data:; "
    "style-src 'self'; script-src 'self'; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
    "form-action 'self'"
)
_CSP_DEV = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; media-src 'self' blob: data:; "
    "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
    "connect-src 'self' ws: http://localhost:* http://127.0.0.1:*; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN001
    if settings.auto_create_tables:
        init_db()
    if settings.seed_on_start:
        from app.bootstrap import ensure_seed_data
        ensure_seed_data()
    yield


def create_app() -> FastAPI:
    if (settings.app_env == "production"
            and settings.secret_key == "CHANGE-ME-LONG-RANDOM-STRING"):
        # JWTs signed with the shipped default would be forgeable by anyone
        # who reads the public repo. Refuse to boot rather than run insecure.
        raise RuntimeError(
            "SECRET_KEY is still the shipped default — set a strong random "
            "value before running in production.")
    app = FastAPI(
        title=settings.app_name,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Action-Token"],
        max_age=600,
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # noqa: ANN001
        # Dev CSP allows the inline assets Swagger/OpenAPI needs; docs are
        # disabled in production where the strict CSP applies.
        csp = _CSP_DEV if settings.docs_enabled else _CSP_PROD
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(self), geolocation=(self)"
        if settings.enable_hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):  # noqa: ANN001
        return JSONResponse(status_code=429,
                            content={"detail": "Too many requests — please retry later."},
                            headers={"Retry-After": "60"})

    from app.core.limits import limiter
    app.state.limiter = limiter

    _register_routers(app)
    return app


def _register_routers(app: FastAPI) -> None:
    from app.api.routes import (
        alerts, auth, cases, cctv, dashboard, demo, evidence, events, health,
        inspections, ops_audit, orgs, projects, qr,
    )
    for module in (health, auth, projects, orgs, dashboard, alerts, cctv,
                   inspections, evidence, qr, events, cases, ops_audit):
        app.include_router(module.router)
    if settings.demo_mode:
        app.include_router(demo.router)


app = create_app()
