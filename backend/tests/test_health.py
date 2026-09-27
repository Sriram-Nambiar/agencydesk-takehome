import pytest


class TestHealthAndObservability:
    def test_liveness_probe(self, client):
        res = client.get("/healthz")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["service"] == "agencydesk-api"

    def test_readiness_probe_with_live_database(self, client):
        res = client.get("/readyz")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ready"
        assert data["database"] == "connected"
        assert data["redis"] in ("connected", "unreachable")

    def test_security_headers_present_on_responses(self, client):
        res = client.get("/healthz")
        assert res.status_code == 200
        headers = res.headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert "Strict-Transport-Security" in headers
        assert "X-XSS-Protection" in headers
        assert "Referrer-Policy" in headers

    def test_request_id_correlation_tracing(self, client):
        # 1. Automatic generation when not provided
        res1 = client.get("/healthz")
        assert "X-Request-ID" in res1.headers
        generated_id = res1.headers["X-Request-ID"]
        assert len(generated_id) > 10

        # 2. Passthrough of incoming X-Request-ID
        custom_id = "trace-req-client-998877"
        res2 = client.get("/healthz", headers={"X-Request-ID": custom_id})
        assert res2.headers.get("X-Request-ID") == custom_id
