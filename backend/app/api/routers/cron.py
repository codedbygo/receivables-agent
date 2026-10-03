"""Vercel Cron (ADR-0015): stands in for the worker loop where no process runs between requests."""

import hmac

from fastapi import APIRouter, Header, Request

from app.core.clock import wall_now
from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.worker.jobs import reap
from app.worker.runner import handlers, schedule, tick

router = APIRouter(tags=["cron"])
BUDGET_S = 240.0  # under the function's maxDuration in vercel.json, so a tick ends between jobs


@router.get("/cron/tick")
def cron_tick(request: Request, authorization: str = Header("")) -> dict[str, int]:
    settings: Settings = request.app.state.settings
    # No secret configured means the route is closed, never open.
    if not settings.cron_secret or not hmac.compare_digest(
        authorization.encode(), f"Bearer {settings.cron_secret}".encode()
    ):
        raise AppError(ErrorCode.UNAUTHORIZED, "Sign in to continue.")
    engine = request.app.state.engine
    schedule(engine, wall_now())
    reap(engine)
    return {"jobs_run": tick(engine, handlers(engine, settings), BUDGET_S)}
