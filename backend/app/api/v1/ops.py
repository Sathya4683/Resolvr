import logging

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.db import SessionLocal

router = APIRouter(tags=["ops"])
log = logging.getLogger(__name__)


@router.get("/health")
def health():
    #liveness only, if the process answers it's alive
    return {"status": "ok"}


@router.get("/ready")
def ready():
    #readiness checks the things we can't work without
    checks = {}
    try:
        with SessionLocal() as db:
            #sql: SELECT 1
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        log.warning("db not ready", extra={"error": str(exc)})
        checks["database"] = "down"

    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"status": "ok" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)


@router.get("/metrics", include_in_schema=False)
def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
