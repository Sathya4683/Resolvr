import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import embeddings, metrics
from app.api.router import api_router
from app.api.v1 import ops
from app.config import settings
from app.logging_setup import request_id_var, setup_logging

setup_logging("api", settings.log_level)
log = logging.getLogger("resolvr.http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    #loading the embedding + reranker models takes a while, do it in the background so the
    #api is up straight away and the first real request doesn't pay for it
    if settings.environment != "test":
        threading.Thread(target=embeddings.warm_up, daemon=True).start()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Resolvr API",
    version="0.1.0",
    description="Semantic resolution assistant for a telecom support desk",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)

#these get hit every few seconds by prometheus / docker, no point logging them
QUIET_PATHS = {"/metrics", "/health", "/ready"}


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        #never leak a stack trace to the client, the request id is enough to find it in the logs
        log.exception("unhandled error")
        response = JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)

    duration = time.perf_counter() - start
    route = request.scope.get("route")
    route_path = getattr(route, "path", "unmatched")
    metrics.HTTP_REQUESTS.labels(request.method, route_path, str(response.status_code)).inc()
    metrics.HTTP_LATENCY.labels(request.method, route_path).observe(duration)

    if request.url.path not in QUIET_PATHS:
        level = logging.WARNING if response.status_code >= 500 else logging.INFO
        log.log(
            level,
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "route": route_path,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 1),
                "user": getattr(request.state, "username", None),
            },
        )
    response.headers["X-Request-ID"] = rid
    request_id_var.reset(token)
    return response


app.include_router(ops.router)
app.include_router(api_router, prefix="/v1")
