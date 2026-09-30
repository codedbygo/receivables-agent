"""FastAPI app factory: request ids, health and readiness (US-01-014)."""

import secrets
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.core.db import make_engine, ping
from app.core.errors import AppError, ErrorCode


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Collections Agent API", version="1.0.0")
    engine = make_engine(settings.database_url)
    app.state.settings = settings
    app.state.engine = engine
    app.state.check_db = lambda: ping(engine)

    @app.middleware("http")
    async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        rid = request.headers.get("X-Request-Id") or f"req_{secrets.token_hex(6)}"
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError) -> JSONResponse:
        return _error(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Anything unnamed is a 500 with the request id; the message never leaks internals.
        return _error(request, 500, ErrorCode.INTERNAL, "Unexpected error. Quote the request id.", [])

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        return {"status": "ok", "checks": {}}

    @app.get("/readyz")
    def readyz() -> JSONResponse:
        ok = bool(app.state.check_db())
        body = {
            "status": "ok" if ok else "unavailable",
            "checks": {"database": "ok" if ok else "unavailable"},
        }
        return JSONResponse(body, status_code=200 if ok else 503)

    return app


def _error(
    request: Request, status: int, code: str, message: str, details: list[dict[str, str]]
) -> JSONResponse:
    rid = getattr(request.state, "request_id", "")
    body = {"error": {"code": code, "message": message, "details": details, "request_id": rid}}
    return JSONResponse(body, status_code=status, headers={"X-Request-Id": rid})
