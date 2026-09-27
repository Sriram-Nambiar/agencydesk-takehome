import pytest


class TestAuth:
    def test_login_success(self, client):
        res = client.post("/auth/login", json={"email": "alex@example.com", "password": "password123"})
        assert res.status_code == 200
        data = res.json()
        assert "token" in data
        assert "user_id" in data

    def test_login_invalid_password(self, client):
        res = client.post("/auth/login", json={"email": "alex@example.com", "password": "wrongpassword"})
        assert res.status_code == 401
        assert "Invalid credentials" in res.json().get("detail", "")

    def test_login_nonexistent_user(self, client):
        res = client.post("/auth/login", json={"email": "nobody@example.com", "password": "password123"})
        assert res.status_code == 401

    def test_get_current_user_me(self, client, admin_token):
        res = client.get("/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        user = res.json()
        assert user["email"] == "alex@example.com"
        assert user["full_name"] == "Alex Rivera"

    def test_get_current_user_unauthorized(self, client):
        res = client.get("/auth/me")
        assert res.status_code == 401

    def test_get_memberships_dual_tenant(self, client, admin_token):
        res = client.get("/auth/memberships", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 200
        memberships = res.json()["memberships"]
        # Alex has memberships in both Acme (admin) and Beta (client)
        assert len(memberships) == 2
        roles = {m["agency_name"]: m["role"] for m in memberships}
        assert roles["Acme Digital Agency"] == "agency_admin"
        assert roles["Beta Media Group"] == "client_user"

    def test_register_new_agency_and_user(self, client):
        payload = {
            "email": "founder@newventure.com",
            "password": "SecurePassword123!",
            "full_name": "New Founder",
            "agency_name": "Venture Studio",
        }
        res = client.post("/auth/register", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "token" in data
        assert "active_agency_id" in data

        # Login with the newly registered user
        login_res = client.post("/auth/login", json={"email": payload["email"], "password": payload["password"]})
        assert login_res.status_code == 200

    def test_register_duplicate_email(self, client):
        payload = {
            "email": "alex@example.com",
            "password": "password123",
            "full_name": "Alex Dupe",
            "agency_name": "Another Agency",
        }
        res = client.post("/auth/register", json=payload)
        assert res.status_code == 400
        assert "already registered" in res.json().get("detail", "").lower()

    def test_register_duplicate_email_case_insensitive(self, client):
        payload = {
            "email": "ALEX@EXAMPLE.COM",
            "password": "password123",
            "full_name": "Alex Uppercase Dupe",
            "agency_name": "Another Agency",
        }
        res = client.post("/auth/register", json=payload)
        assert res.status_code == 400
        assert "already registered" in res.json().get("detail", "").lower()
