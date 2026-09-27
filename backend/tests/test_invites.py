import uuid
import pytest


class TestAgencyInvites:
    def test_create_invite_staff(self, client, admin_acme_headers):
        payload = {
            "email": "designer@acme.com",
            "role": "agency_member",
        }
        res = client.post("/agency/invites", json=payload, headers=admin_acme_headers)
        assert res.status_code == 200
        data = res.json()
        assert "invite" in data
        invite = data["invite"]
        assert invite["email"] == "designer@acme.com"
        assert invite["role"] == "agency_member"
        assert "token" in invite
        assert "expires_at" in invite

    def test_create_invite_client_user(self, client, admin_acme_headers, sample_client):
        payload = {
            "email": "stakeholder@starlight.com",
            "role": "client_user",
            "client_id": sample_client["id"],
        }
        res = client.post("/agency/invites", json=payload, headers=admin_acme_headers)
        assert res.status_code == 200
        invite = res.json()["invite"]
        assert invite["email"] == "stakeholder@starlight.com"
        assert invite["role"] == "client_user"
        assert invite["client_id"] == sample_client["id"]

    def test_create_invite_non_admin_forbidden(self, client, member_acme_headers, client_acme_headers):
        payload = {"email": "test@acme.com", "role": "agency_member"}

        res_member = client.post("/agency/invites", json=payload, headers=member_acme_headers)
        assert res_member.status_code == 403
        assert "Only agency admins may invite users" in res_member.json().get("detail", "")

        res_client = client.post("/agency/invites", json=payload, headers=client_acme_headers)
        assert res_client.status_code == 403

    def test_create_invite_validation(self, client, admin_acme_headers, sample_client):
        # Invalid email
        res = client.post("/agency/invites", json={"email": "bad-email", "role": "agency_member"}, headers=admin_acme_headers)
        assert res.status_code == 400

        # Invalid role
        res = client.post("/agency/invites", json={"email": "test@test.com", "role": "superadmin"}, headers=admin_acme_headers)
        assert res.status_code == 400

        # client_user without client_id
        res = client.post("/agency/invites", json={"email": "client@test.com", "role": "client_user"}, headers=admin_acme_headers)
        assert res.status_code == 400
        assert "Client invites require a client" in res.json().get("detail", "")

        # staff invite with client_id
        res = client.post(
            "/agency/invites",
            json={"email": "staff@test.com", "role": "agency_member", "client_id": sample_client["id"]},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

        # client_id from another agency
        foreign_client_id = str(uuid.uuid4())
        res = client.post(
            "/agency/invites",
            json={"email": "client@test.com", "role": "client_user", "client_id": foreign_client_id},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

    def test_invite_resend_updates_token(self, client, admin_acme_headers):
        email = "resend_probe@example.com"

        # First invite
        res1 = client.post(
            "/agency/invites",
            json={"email": email, "role": "agency_member"},
            headers=admin_acme_headers,
        )
        assert res1.status_code == 200
        token1 = res1.json()["invite"]["token"]

        # Resend invite to same email (case insensitive)
        res2 = client.post(
            "/agency/invites",
            json={"email": email.upper(), "role": "agency_member"},
            headers=admin_acme_headers,
        )
        assert res2.status_code == 200
        token2 = res2.json()["invite"]["token"]

        # Token was refreshed
        assert token1 != token2

    def test_accept_invite_new_user(self, client, admin_acme_headers):
        email = "onboarding_newbie@acme.com"
        create_res = client.post(
            "/agency/invites",
            json={"email": email, "role": "agency_member"},
            headers=admin_acme_headers,
        )
        assert create_res.status_code == 200
        token = create_res.json()["invite"]["token"]

        # Accept invite as a brand new user
        accept_payload = {
            "token": token,
            "password": "BrandNewPassword123!",
            "full_name": "Onboarding Newbie",
        }
        accept_res = client.post("/invites/accept", json=accept_payload)
        assert accept_res.status_code == 200
        data = accept_res.json()
        assert "token" in data
        assert "user_id" in data
        assert data["role"] == "agency_member"

        # Log in with the newly created account
        login_res = client.post(
            "/auth/login",
            json={"email": email, "password": "BrandNewPassword123!"},
        )
        assert login_res.status_code == 200

    def test_accept_invite_existing_user_in_acme(self, client, admin_acme_headers):
        # First register an independent user
        client.post(
            "/auth/register",
            json={
                "email": "independent_dev@tech.com",
                "password": "ExistingUserPassword123!",
                "full_name": "Independent Dev",
                "agency_name": "Independent Shop",
            }
        )

        # Admin invites this existing user into Acme
        invite_res = client.post(
            "/agency/invites",
            json={"email": "independent_dev@tech.com", "role": "agency_member"},
            headers=admin_acme_headers,
        )
        token = invite_res.json()["invite"]["token"]

        # Wrong password fails
        bad_pw_res = client.post(
            "/invites/accept",
            json={"token": token, "password": "wrong_password"},
        )
        assert bad_pw_res.status_code == 401
        assert "Sign in with the existing account password" in bad_pw_res.json().get("detail", "")

        # Correct password succeeds
        good_res = client.post(
            "/invites/accept",
            json={"token": token, "password": "ExistingUserPassword123!"},
        )
        assert good_res.status_code == 200

        # Repeating acceptance is idempotent
        repeat_res = client.post(
            "/invites/accept",
            json={"token": token, "password": "ExistingUserPassword123!"},
        )
        assert repeat_res.status_code == 200

    def test_accept_invite_invalid_token(self, client):
        res = client.post(
            "/invites/accept",
            json={"token": "nonexistent_token_12345", "password": "anypassword"},
        )
        assert res.status_code == 404
