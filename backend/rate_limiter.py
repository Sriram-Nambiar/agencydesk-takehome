import time
import logging
import uuid
from typing import Callable
from fastapi import Request, HTTPException, Depends
from redis_client import get_redis

logger = logging.getLogger(__name__)


def is_rate_limited(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """
    Sliding window rate limiter backed by Redis sorted sets (ZSET).
    Returns (is_limited: bool, retry_after_seconds: int).
    """
    try:
        r = get_redis()
        if r is None:
            # If Redis is temporarily down, fail open to prevent blocking legitimate traffic
            return False, 0

        now = time.time()
        window_start = now - window_seconds
        redis_key = f"agencydesk:ratelimit:{key}"

        pipe = r.pipeline()
        # 1. Remove timestamps older than the current sliding window
        pipe.zremrangebyscore(redis_key, 0, window_start)
        # 2. Count requests in the current window
        pipe.zcard(redis_key)
        # 3. Add current timestamp
        # Use a unique member per request; multiple calls may share the same
        # clock tick, and ZSET members must not overwrite each other.
        pipe.zadd(redis_key, {f"{now}:{uuid.uuid4()}": now})
        # 4. Set expiry on the set to auto-clean up idle keys
        pipe.expire(redis_key, window_seconds + 5)
        results = pipe.execute()

        request_count = results[1]

        if request_count >= limit:
            # Compute time until the oldest request falls outside the window
            oldest_entries = r.zrange(redis_key, 0, 0, withscores=True)
            if oldest_entries:
                oldest_ts = oldest_entries[0][1]
                retry_after = max(1, int(oldest_ts + window_seconds - now))
            else:
                retry_after = window_seconds
            return True, retry_after

        return False, 0
    except Exception as exc:
        logger.warning(f"Rate limiting check failed: {exc}")
        return False, 0


def rate_limit(limit: int, window_seconds: int) -> Callable:
    """FastAPI dependency factory enforcing a sliding-window rate limit per client IP."""
    async def dependency(request: Request):
        # Extract client IP, prioritizing standard reverse-proxy headers
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        elif request.client and request.client.host:
            client_ip = request.client.host
        else:
            client_ip = "127.0.0.1"

        endpoint = request.url.path
        key = f"{endpoint}:{client_ip}"

        limited, retry_after = is_rate_limited(key, limit, window_seconds)
        if limited:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please slow down and try again.",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency
