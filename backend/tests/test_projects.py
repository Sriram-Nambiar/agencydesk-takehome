import uuid
import pytest


class TestProjects:
    def test_list_projects_as_admin(self, client, admin_acme_headers):
        res = client.get("/projects", headers=admin_acme_headers)
        assert res.status_code == 200
        data = res.json()
        assert "projects" in data
        assert len(data["projects"]) >= 1

        project = next((p for p in data["projects"] if p["name"] == "Website Redesign"), None)
        assert project is not None
        assert project["client_name"] == "Starlight Tech"
        assert "task_count" in project
        assert "completed_task_count" in project
        assert "total_hours_logged" in project
        assert project["total_hours_logged"] >= 0

    def test_list_projects_as_member(self, client, member_acme_headers):
        res = client.get("/projects", headers=member_acme_headers)
        assert res.status_code == 200
        projects = res.json()["projects"]
        # Sarah is assigned to Website Redesign
        project_names = [p["name"] for p in projects]
        assert "Website Redesign" in project_names

    def test_list_projects_as_client_forbidden(self, client, client_acme_headers):
        res = client.get("/projects", headers=client_acme_headers)
        assert res.status_code == 403
        assert "Client users must use /portal endpoints" in res.json().get("detail", "")

    def test_list_projects_missing_agency_header(self, client, admin_token):
        res = client.get("/projects", headers={"Authorization": f"Bearer {admin_token}"})
        assert res.status_code == 400
        assert "Missing X-Agency-ID header" in res.json().get("detail", "")

    def test_get_project_detail_as_admin(self, client, admin_acme_headers, sample_entities):
        project_id = sample_entities["project"]["id"]
        res = client.get(f"/projects/{project_id}", headers=admin_acme_headers)
        assert res.status_code == 200
        data = res.json()
        assert "project" in data
        assert data["project"]["name"] == "Website Redesign"
        assert "tasks" in data
        assert "total_hours_logged" in data

        # Admin must see both internal and client-visible tasks
        tasks = data["tasks"]
        internal_tasks = [t for t in tasks if t["is_internal"]]
        public_tasks = [t for t in tasks if not t["is_internal"]]
        assert len(internal_tasks) >= 1
        assert len(public_tasks) >= 1

    def test_get_project_detail_as_member_assigned(self, client, member_acme_headers, sample_entities):
        project_id = sample_entities["project"]["id"]
        res = client.get(f"/projects/{project_id}", headers=member_acme_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["project"]["id"] == project_id

    def test_get_project_detail_as_client_forbidden(self, client, client_acme_headers, sample_entities):
        project_id = sample_entities["project"]["id"]
        res = client.get(f"/projects/{project_id}", headers=client_acme_headers)
        assert res.status_code == 403

    def test_get_project_nonexistent_uuid(self, client, admin_acme_headers):
        random_id = str(uuid.uuid4())
        res = client.get(f"/projects/{random_id}", headers=admin_acme_headers)
        assert res.status_code == 404

    def test_get_project_cross_tenant_returns_404(self, client, admin_acme_headers, admin_beta_headers):
        # Fetch Beta's project using Alex's client portal in Beta
        beta_portal = client.get("/portal/projects", headers=admin_beta_headers)
        assert beta_portal.status_code == 200
        beta_projects = beta_portal.json()["projects"]
        assert len(beta_projects) >= 1
        beta_proj_id = beta_projects[0]["id"]

        # Attempt to access Beta project using Acme's agency workspace header -> 404
        res = client.get(f"/projects/{beta_proj_id}", headers=admin_acme_headers)
        assert res.status_code == 404


    def test_project_member_lifecycle(
        self, client, admin_acme_headers, member_acme_headers, sample_entities, sarah_user_id
    ):
        project_id = sample_entities["project"]["id"]

        # 1. Non-admin cannot remove project member
        forbidden_del = client.delete(
            f"/projects/{project_id}/members/{sarah_user_id}",
            headers=member_acme_headers
        )
        assert forbidden_del.status_code == 403

        # 2. Admin removes member
        del_res = client.delete(
            f"/projects/{project_id}/members/{sarah_user_id}?unassign_active=false",
            headers=admin_acme_headers
        )
        assert del_res.status_code == 200
        assert del_res.json()["access"] == "removed"

        # 3. Member no longer sees project
        list_res = client.get("/projects", headers=member_acme_headers)
        assert list_res.status_code == 200
        member_projects = list_res.json()["projects"]
        assert not any(p["id"] == project_id for p in member_projects)

        # 4. Member getting project detail now returns 404
        get_res = client.get(f"/projects/{project_id}", headers=member_acme_headers)
        assert get_res.status_code == 404

        # 5. Task assignment history preserved (assignee_id not cleared)
        admin_view = client.get(f"/projects/{project_id}", headers=admin_acme_headers)
        assert admin_view.status_code == 200
        tasks = admin_view.json()["tasks"]
        assigned_to_sarah = [t for t in tasks if t["assignee_id"] == sarah_user_id]
        assert len(assigned_to_sarah) >= 1

        # 6. Non-admin cannot add member
        forbidden_put = client.put(
            f"/projects/{project_id}/members/{sarah_user_id}",
            headers=member_acme_headers
        )
        assert forbidden_put.status_code == 403

        # 7. Admin restores member
        add_res = client.put(
            f"/projects/{project_id}/members/{sarah_user_id}",
            headers=admin_acme_headers
        )
        assert add_res.status_code == 200
        assert add_res.json()["access"] == "assigned"

        # 8. Idempotent repeat PUT
        add_repeat = client.put(
            f"/projects/{project_id}/members/{sarah_user_id}",
            headers=admin_acme_headers
        )
        assert add_repeat.status_code == 200
        assert add_repeat.json()["access"] == "assigned"

        # 9. Sarah sees project again
        restored_list = client.get("/projects", headers=member_acme_headers)
        assert any(p["id"] == project_id for p in restored_list.json()["projects"])

    def test_add_or_remove_invalid_member(self, client, admin_acme_headers, sample_entities):
        project_id = sample_entities["project"]["id"]
        fake_user_id = str(uuid.uuid4())

        del_res = client.delete(f"/projects/{project_id}/members/{fake_user_id}", headers=admin_acme_headers)
        assert del_res.status_code == 404

        put_res = client.put(f"/projects/{project_id}/members/{fake_user_id}", headers=admin_acme_headers)
        assert put_res.status_code == 404

    def test_remove_member_with_unassign_active(
        self, client, admin_acme_headers, sample_entities, sarah_user_id
    ):
        project_id = sample_entities["project"]["id"]

        # Ensure Sarah is assigned to project
        client.put(f"/projects/{project_id}/members/{sarah_user_id}", headers=admin_acme_headers)

        # Create an active task assigned to Sarah
        active_task_res = client.post(
            "/tasks",
            headers=admin_acme_headers,
            json={
                "project_id": project_id,
                "title": "Active Work to be Unassigned",
                "status": "in_progress",
                "assignee_id": sarah_user_id,
                "is_internal": False,
            }
        )
        assert active_task_res.status_code == 200
        active_task_id = active_task_res.json()["id"]

        # Create a completed task assigned to Sarah
        done_task_res = client.post(
            "/tasks",
            headers=admin_acme_headers,
            json={
                "project_id": project_id,
                "title": "Completed Work History",
                "status": "done",
                "assignee_id": sarah_user_id,
                "is_internal": False,
            }
        )
        assert done_task_res.status_code == 200
        done_task_id = done_task_res.json()["id"]

        # Remove Sarah with unassign_active=True
        del_res = client.delete(
            f"/projects/{project_id}/members/{sarah_user_id}",
            headers=admin_acme_headers
        )
        assert del_res.status_code == 200
        assert del_res.json()["unassigned_tasks"] >= 1

        # Check project tasks
        admin_view = client.get(f"/projects/{project_id}", headers=admin_acme_headers)
        assert admin_view.status_code == 200
        tasks_by_id = {t["id"]: t for t in admin_view.json()["tasks"]}

        # Active task was unassigned
        assert tasks_by_id[active_task_id]["assignee_id"] is None
        # Done task retained historical assignee
        assert tasks_by_id[done_task_id]["assignee_id"] == sarah_user_id

        # Restore Sarah to project for subsequent tests
        client.put(f"/projects/{project_id}/members/{sarah_user_id}", headers=admin_acme_headers)
