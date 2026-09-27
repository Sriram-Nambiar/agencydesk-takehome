import os
import json
import logging
from typing import Any, Optional
import redis

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

_redis_pool: Optional[redis.ConnectionPool] = None


def get_redis_pool() -> redis.ConnectionPool:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.ConnectionPool(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
    return _redis_pool


def get_redis() -> Optional[redis.Redis]:
    """Return a Redis client instance from connection pool, or None if connection fails."""
    try:
        pool = get_redis_pool()
        client = redis.Redis(connection_pool=pool)
        return client
    except Exception as exc:
        logger.warning(f"Could not connect to Redis: {exc}")
        return None


def close_redis_pool():
    global _redis_pool
    if _redis_pool is not None:
        try:
            _redis_pool.disconnect()
        except Exception:
            pass
        _redis_pool = None


def ping_redis() -> bool:
    """Return True if Redis responds to ping, False otherwise."""
    try:
        r = get_redis()
        if r is None:
            return False
        return bool(r.ping())
    except Exception:
        return False


def publish_event(channel: str, event_data: dict[str, Any]) -> bool:
    """
    Publish an event to a Redis Pub/Sub channel and push to the persistent event queue.
    Returns True if published, False if Redis is unreachable.
    """
    try:
        r = get_redis()
        if r is None:
            return False
        payload = json.dumps(event_data, default=str)
        # 1. Publish to real-time pub/sub channel
        r.publish(channel, payload)
        # 2. Push to persistent automation/notification FIFO stream/queue
        r.rpush("agencydesk:events_queue", payload)
        return True
    except Exception as exc:
        logger.warning(f"Failed to publish Redis event on {channel}: {exc}")
        return False


def cache_unread_count(agency_id: str, user_id: str, count: int, ttl: int = 300) -> bool:
    """Cache the unread notification count for rapid UI badge retrieval."""
    try:
        r = get_redis()
        if r is None:
            return False
        key = f"agencydesk:unread:{agency_id}:{user_id}"
        r.set(key, count, ex=ttl)
        return True
    except Exception:
        return False


def get_cached_unread_count(agency_id: str, user_id: str) -> Optional[int]:
    """Retrieve cached unread count if available."""
    try:
        r = get_redis()
        if r is None:
            return None
        val = r.get(f"agencydesk:unread:{agency_id}:{user_id}")
        return int(val) if val is not None else None
    except Exception:
        return None


def invalidate_unread_cache(agency_id: str, user_id: str) -> bool:
    """Invalidate cached unread count when notifications are created or read."""
    try:
        r = get_redis()
        if r is None:
            return False
        r.delete(f"agencydesk:unread:{agency_id}:{user_id}")
        return True
    except Exception:
        return False
