import uuid
import pytest


class TestPortal:
    def test_portal_list_projects_as_client(self, client, client_acme_headers):
        res = client.get("/portal/projects", headers=client_acme_headers)
        assert res.status_code == 200
        data = res.json()
        assert "projects" in data
        assert len(data["projects"]) >= 1

        # All projects returned must belong to client's client_id (Starlight Tech)
        for proj in data["projects"]:
            assert proj["client_name"] == "Starlight Tech"
            assert "task_count" in proj
            assert "completed_task_count" in proj

    def test_portal_list_projects_task_counts_exclude_internal(
        self, client, client_acme_headers, admin_acme_headers, sample_entities
    ):
        """Verify that portal task count only reflects non-internal tasks."""
        proj_id = sample_entities["project"]["id"]

        # Admin view (sees total tasks)
        admin_res = client.get("/projects", headers=admin_acme_headers)
        admin_proj = next(p for p in admin_res.json()["projects"] if p["id"] == proj_id)

        # Client view (only sees public tasks)
        client_res = client.get("/portal/projects", headers=client_acme_headers)
        client_proj = next(p for p in client_res.json()["projects"] if p["id"] == proj_id)

        # In seed data, 1 task is internal and 1 is public, so admin task_count >= 2, client task_count == 1
        assert admin_proj["task_count"] > client_proj["task_count"]

    def test_portal_get_project_leak_shield(self, client, client_acme_headers, sample_entities):
        """Verify strict leak-shielding: 100% of internal tasks must be omitted."""
        proj_id = sample_entities["project"]["id"]
        res = client.get(f"/portal/projects/{proj_id}", headers=client_acme_headers)
        assert res.status_code == 200
        data = res.json()
        assert "project" in data
        assert "tasks" in data

        tasks = data["tasks"]
        titles = [t["title"] for t in tasks]

        # The internal task 'DB Query Optimization' MUST NOT appear
        assert "DB Query Optimization" not in titles
        # The public task 'Homepage Figma Mockup' MUST appear
        assert "Homepage Figma Mockup" in titles

        # Ensure returned task fields match safe public projection
        for task in tasks:
            assert "id" in task
            assert "title" in task
            assert "status" in task
            assert "priority" in task
            # is_internal shouldn't even be exposed or should not be true
            assert task.get("is_internal") is not True

    def test_portal_cross_client_isolation(self, client, client_acme_headers, admin_beta_headers):
        """Client cannot access another client's project via portal."""
        # Beta Media Group has Nike Retail's project
        beta_portal = client.get("/portal/projects", headers=admin_beta_headers)
        beta_proj_id = beta_portal.json()["projects"][0]["id"]

        # John (Starlight Tech client in Acme) tries to access Nike project with Acme header
        res = client.get(f"/portal/projects/{beta_proj_id}", headers=client_acme_headers)
        assert res.status_code == 404

    def test_portal_staff_access(self, client, admin_acme_headers, sample_entities):
        """Agency admin can view portal perspective for any agency project."""
        proj_id = sample_entities["project"]["id"]
        res = client.get(f"/portal/projects/{proj_id}", headers=admin_acme_headers)
        assert res.status_code == 200
        # Even when accessed by staff, portal endpoint enforces leak shield on tasks
        titles = [t["title"] for t in res.json()["tasks"]]
        assert "DB Query Optimization" not in titles
        assert "Homepage Figma Mockup" in titles

    def test_portal_missing_agency_header(self, client, client_token):
        res = client.get("/portal/projects", headers={"Authorization": f"Bearer {client_token}"})
        assert res.status_code == 400
        assert "Missing X-Agency-ID header" in res.json().get("detail", "")

    def test_portal_invalid_uuid(self, client, client_acme_headers):
        res = client.get("/portal/projects/not-a-valid-uuid", headers=client_acme_headers)
        assert res.status_code == 400
        assert "valid UUID" in res.json().get("detail", "")
