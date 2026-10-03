"""
Fixed-window rate limits in redis, per user and per route group:
    key = rl:<group>:<user id>:<current minute>
INCR the key, set it to expire after the window, reject once the count goes over the limit.
If redis is down we let the request through (fail open) and log it, limits shouldn't take the app down.
"""

import logging
import time

import redis
from fastapi import Depends, HTTPException, status

from app.config import settings
from app.deps import get_current_user
from app.models import User

log = logging.getLogger(__name__)
_client = redis.Redis.from_url(settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)

WINDOW_SECONDS = 60


def limit_for(group: str, role: str) -> int:
    base = {
        "analyze": settings.rate_limit_analyze_per_min,
        "chat": settings.rate_limit_chat_per_min,
        "batch": settings.rate_limit_batch_per_min,
    }.get(group, settings.rate_limit_default_per_min)
    #admins get a bit more room, they demo and test things
    return base * 2 if role == "admin" else base


def check(group: str, user: User) -> None:
    window = int(time.time() // WINDOW_SECONDS)
    key = f"rl:{group}:{user.id}:{window}"
    try:
        pipe = _client.pipeline()
        pipe.incr(key)
        pipe.expire(key, WINDOW_SECONDS)
        count = pipe.execute()[0]
    except redis.RedisError as exc:
        log.warning("rate limiter unavailable, allowing request", extra={"error": str(exc)[:200]})
        return
    if count > limit_for(group, user.role):
        retry_after = WINDOW_SECONDS - int(time.time()) % WINDOW_SECONDS
        log.info("rate limited", extra={"group": group, "user": user.username})
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many requests, try again in {retry_after}s",
            headers={"Retry-After": str(retry_after)},
        )


def rate_limit(group: str):
    """use as a route dependency: dependencies=[Depends(rate_limit("analyze"))]"""

    def dependency(user: User = Depends(get_current_user)) -> None:
        check(group, user)

    return dependency
