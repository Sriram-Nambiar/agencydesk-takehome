import pytest
import rate_limiter


class FakePipeline:
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self.commands = []

    def zremrangebyscore(self, key, minimum, maximum):
        self.commands.append(("zremrangebyscore", key, minimum, maximum))
        return self

    def zcard(self, key):
        self.commands.append(("zcard", key))
        return self

    def zadd(self, key, values):
        self.commands.append(("zadd", key, values))
        return self

    def expire(self, key, seconds):
        self.commands.append(("expire", key, seconds))
        return self

    def execute(self):
        results = []
        for command in self.commands:
            name, *args = command
            results.append(getattr(self.redis_client, name)(*args))
        return results


class FakeRedis:
    def __init__(self):
        self.sorted_sets = {}

    def pipeline(self):
        return FakePipeline(self)

    def zremrangebyscore(self, key, minimum, maximum):
        entries = self.sorted_sets.setdefault(key, {})
        expired = [member for member, score in entries.items() if minimum <= score <= maximum]
        for member in expired:
            del entries[member]
        return len(expired)

    def zcard(self, key):
        return len(self.sorted_sets.get(key, {}))

    def zadd(self, key, values):
        self.sorted_sets.setdefault(key, {}).update(values)

    def expire(self, _key, _seconds):
        return True

    def zrange(self, key, start, stop, withscores=False):
        entries = sorted(self.sorted_sets.get(key, {}).items(), key=lambda item: item[1])
        selected = entries[start:stop + 1]
        return selected if withscores else [member for member, _ in selected]


@pytest.fixture
def fake_redis(monkeypatch):
    instance = FakeRedis()
    now = [1000.0]
    monkeypatch.setattr(rate_limiter.time, "time", lambda: now[0])
    monkeypatch.setattr(rate_limiter, "get_redis", lambda: instance)
    instance.advance_clock = lambda seconds: now.__setitem__(0, now[0] + seconds)
    return instance


class TestRateLimiter:
    def test_sliding_window_allows_within_threshold(self, fake_redis):
        key = "test_window"
        limit = 3
        window = 5

        # First 3 calls succeed
        assert rate_limiter.is_rate_limited(key, limit, window)[0] is False
        assert rate_limiter.is_rate_limited(key, limit, window)[0] is False
        assert rate_limiter.is_rate_limited(key, limit, window)[0] is False

        # 4th call is rate limited
        limited, retry_after = rate_limiter.is_rate_limited(key, limit, window)
        assert limited is True
        assert retry_after > 0
        assert retry_after <= window

    def test_rate_limiter_clean_reset_after_window(self, fake_redis):
        key = "test_expire"
        limit = 2
        window = 1

        assert rate_limiter.is_rate_limited(key, limit, window)[0] is False
        assert rate_limiter.is_rate_limited(key, limit, window)[0] is False
        assert rate_limiter.is_rate_limited(key, limit, window)[0] is True

        # Sleep past window
        fake_redis.advance_clock(1.1)

        # Should be allowed again
        assert rate_limiter.is_rate_limited(key, limit, window)[0] is False

    def test_rate_limit_http_429_on_login(self, client, fake_redis):
        """Simulate rapid brute-force attempts from same client IP to verify HTTP 429."""
        from fastapi import FastAPI
        from rate_limiter import rate_limit
        from fastapi.testclient import TestClient

        test_app = FastAPI()

        @test_app.post("/test-auth", dependencies=[pytest.importorskip("fastapi").Depends(rate_limit(limit=2, window_seconds=2))])
        def test_endpoint():
            return {"status": "ok"}

        tc = TestClient(test_app)
        headers = {"X-Forwarded-For": "198.51.100.99"}

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
