import time
import pytest
from rate_limiter import is_rate_limited
from redis_client import get_redis


class TestRateLimiter:
    def test_sliding_window_allows_within_threshold(self):
        key = f"test_window_{time.time()}"
        limit = 3
        window = 5

        # First 3 calls succeed
        assert is_rate_limited(key, limit, window)[0] is False
        assert is_rate_limited(key, limit, window)[0] is False
        assert is_rate_limited(key, limit, window)[0] is False

        # 4th call is rate limited
        limited, retry_after = is_rate_limited(key, limit, window)
        assert limited is True
        assert retry_after > 0
        assert retry_after <= window

    def test_rate_limiter_clean_reset_after_window(self):
        key = f"test_expire_{time.time()}"
        limit = 2
        window = 1

        assert is_rate_limited(key, limit, window)[0] is False
        assert is_rate_limited(key, limit, window)[0] is False
        assert is_rate_limited(key, limit, window)[0] is True

        # Sleep past window
        time.sleep(1.1)

        # Should be allowed again
        assert is_rate_limited(key, limit, window)[0] is False

    def test_rate_limit_http_429_on_login(self, client):
        """Simulate rapid brute-force attempts from same client IP to verify HTTP 429."""
        from fastapi import FastAPI
        from rate_limiter import rate_limit
        from fastapi.testclient import TestClient

        test_app = FastAPI()

        @test_app.post("/test-auth", dependencies=[pytest.importorskip("fastapi").Depends(rate_limit(limit=2, window_seconds=2))])
        def test_endpoint():
            return {"status": "ok"}

        tc = TestClient(test_app)
        headers = {"X-Forwarded-For": f"198.51.100.{int(time.time()) % 250}"}

        # 1st request -> 200
        r1 = tc.post("/test-auth", headers=headers)
        assert r1.status_code == 200

        # 2nd request -> 200
        r2 = tc.post("/test-auth", headers=headers)
        assert r2.status_code == 200

        # 3rd request -> 429 Too Many Requests
        r3 = tc.post("/test-auth", headers=headers)
        assert r3.status_code == 429
        assert "Retry-After" in r3.headers
        assert "Too many requests" in r3.json()["detail"]
