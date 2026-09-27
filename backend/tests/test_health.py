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

    def test_process_time_header_and_structured_latency_logging(self, client, caplog):
        import logging
        with caplog.at_level(logging.INFO):
            res = client.get("/healthz", headers={"X-Request-ID": "test-latency-123"})
            assert res.status_code == 200
            assert "X-Process-Time" in res.headers
            process_time = res.headers["X-Process-Time"]
            assert process_time.endswith("ms")
            latency_val = float(process_time[:-2])
            assert latency_val >= 0.0

            # Verify structured log output was generated
            log_messages = [rec.message for rec in caplog.records if "test-latency-123" in rec.message]
            assert len(log_messages) >= 1
            log_msg = log_messages[0]
            assert "request_id=test-latency-123" in log_msg
            assert "method=GET" in log_msg
            assert "path=/healthz" in log_msg
            assert "status=200" in log_msg
            assert "latency_ms=" in log_msg
