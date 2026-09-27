import uuid
import pytest


class TestTenantIsolation:
    def test_unauthenticated_requests_fail(self, client):
        endpoints = [
            ("GET", "/auth/me"),
            ("GET", "/auth/memberships"),
            ("GET", "/projects"),
            ("GET", "/portal/projects"),
            ("POST", "/tasks"),
            ("GET", "/agency/members"),
            ("GET", "/agency/clients"),
            ("POST", "/agency/invites"),
        ]
        for method, endpoint in endpoints:
            if method == "GET":
                res = client.get(endpoint)
            else:
                res = client.post(endpoint, json={})
            assert res.status_code == 401, f"{method} {endpoint} did not return 401 without token: {res.status_code}"

    def test_missing_agency_header_fails_fast(self, client, admin_token, sample_entities):
        headers = {"Authorization": f"Bearer {admin_token}"}
        proj_id = sample_entities["project"]["id"]

        # GET endpoints
        get_endpoints = [
            "/projects",
            f"/projects/{proj_id}",
            "/portal/projects",
            f"/portal/projects/{proj_id}",
            "/agency/members",
            "/agency/clients",
        ]
        for ep in get_endpoints:
            res = client.get(ep, headers=headers)
            assert res.status_code == 400, f"GET {ep} did not return 400: {res.status_code}"
            assert "Missing X-Agency-ID" in res.json().get("detail", "")

        # POST endpoints with valid body but missing header
        post_cases = [
            ("/tasks", {"project_id": proj_id, "title": "Test Task"}),
            ("/agency/invites", {"email": "invitee@example.com", "role": "agency_member"}),
        ]
        for ep, payload in post_cases:
            res = client.post(ep, json=payload, headers=headers)
            assert res.status_code == 400, f"POST {ep} did not return 400: {res.status_code}"
            assert "Missing X-Agency-ID" in res.json().get("detail", "")

    def test_malformed_agency_id_returns_400(self, client, admin_token):
        headers = {
            "Authorization": f"Bearer {admin_token}",
            "X-Agency-ID": "not-a-valid-uuid",
        }
        res = client.get("/projects", headers=headers)
        assert res.status_code == 400
        assert "valid UUID" in res.json().get("detail", "")

    def test_foreign_agency_tenant_access_denied(self, client, member_token, agencies):
        # Sarah is member of Acme only, not Beta
        headers = {
            "Authorization": f"Bearer {member_token}",
            "X-Agency-ID": agencies["beta"],
        }
        res = client.get("/projects", headers=headers)
        assert res.status_code == 403
        assert "Access denied to this agency tenant" in res.json().get("detail", "")

    def test_sql_injection_and_uuid_parameter_hardening(self, client, admin_acme_headers):
        # Payloads targeting UUID parsing and SQL injection
        attack_payloads = [
            "' OR '1'='1",
            "1; DROP TABLE tasks; --",
            "' UNION SELECT * FROM users--",
            "non-uuid-string-payload",
        ]

        for payload in attack_payloads:
            # 1. Project detail
            r1 = client.get(f"/projects/{payload}", headers=admin_acme_headers)
            assert r1.status_code == 400, f"Expected 400 for {payload}, got {r1.status_code}"
            assert "valid UUID" in r1.json().get("detail", "")

            # 2. Task comments
            r2 = client.get(f"/tasks/{payload}/comments", headers=admin_acme_headers)
            assert r2.status_code == 400
            assert "valid UUID" in r2.json().get("detail", "")

            # 3. Task files
            r3 = client.get(f"/tasks/{payload}/files", headers=admin_acme_headers)
            assert r3.status_code == 400
            assert "valid UUID" in r3.json().get("detail", "")

            # 4. Task time entries
            r4 = client.get(f"/tasks/{payload}/time", headers=admin_acme_headers)
            assert r4.status_code == 400
            assert "valid UUID" in r4.json().get("detail", "")

            # 5. File approval
            r5 = client.patch(f"/files/{payload}/approval", json={"approval_status": "approved"}, headers=admin_acme_headers)
            assert r5.status_code == 400
            assert "valid UUID" in r5.json().get("detail", "")

