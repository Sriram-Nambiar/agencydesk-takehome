import pytest


class TestAgencyDirectory:
    def test_get_members_as_admin(self, client, admin_acme_headers):
        res = client.get("/agency/members", headers=admin_acme_headers)
        assert res.status_code == 200
        members = res.json()["members"]
        assert len(members) >= 2
        emails = [m["email"] for m in members]
        assert "alex@example.com" in emails
        assert "sarah@acme.com" in emails

    def test_get_members_as_member(self, client, member_acme_headers):
        res = client.get("/agency/members", headers=member_acme_headers)
        assert res.status_code == 200
        members = res.json()["members"]
        assert len(members) >= 1

    def test_get_members_as_client_forbidden(self, client, client_acme_headers):
        res = client.get("/agency/members", headers=client_acme_headers)
        assert res.status_code == 403
        assert "Client users cannot view agency staff directory" in res.json().get("detail", "")

    def test_get_members_missing_agency_header(self, client, admin_token):
        res = client.get("/agency/members", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 400
        assert "Missing X-Agency-ID header" in res.json().get("detail", "")

    def test_get_clients_as_admin(self, client, admin_acme_headers):
        res = client.get("/agency/clients", headers=admin_acme_headers)
        assert res.status_code == 200
        clients = res.json()["clients"]
        assert len(clients) >= 1
        assert any(c["name"] == "Starlight Tech" for c in clients)

    def test_get_clients_as_member(self, client, member_acme_headers):
        res = client.get("/agency/clients", headers=member_acme_headers)
        assert res.status_code == 200
        clients = res.json()["clients"]
        assert any(c["name"] == "Starlight Tech" for c in clients)

    def test_get_clients_as_client(self, client, client_acme_headers):
        res = client.get("/agency/clients", headers=client_acme_headers)
        assert res.status_code == 200
        clients = res.json()["clients"]
        # Client user only sees their own client organization
        assert len(clients) == 1
        assert clients[0]["name"] == "Starlight Tech"

    def test_get_clients_missing_agency_header(self, client, client_token):
        res = client.get("/agency/clients", headers={"Authorization": f"Bearer {client_token}"})
        assert res.status_code == 400
