import uuid
import pytest


class TestTasks:
    def test_create_task_as_admin_public_and_internal(self, client, admin_acme_headers, sample_entities, sarah_user_id):
        proj_id = sample_entities["project"]["id"]

        # 1. Create public task
        public_payload = {
            "project_id": proj_id,
            "title": "Design QA Checklist",
            "status": "todo",
            "priority": "high",
            "due_date": "2026-11-01",
            "assignee_id": sarah_user_id,
            "is_internal": False,
        }
        res_pub = client.post("/tasks", json=public_payload, headers=admin_acme_headers)
        assert res_pub.status_code == 200
        pub_task = res_pub.json()
        assert pub_task["title"] == "Design QA Checklist"
        assert pub_task["is_internal"] is False
        assert pub_task["status"] == "todo"
        assert pub_task["priority"] == "high"

        # 2. Create internal task
        internal_payload = {
            "project_id": proj_id,
            "title": "Internal Server Migrations",
            "status": "in_progress",
            "priority": "urgent",
            "due_date": "2026-11-15",
            "is_internal": True,
        }
        res_int = client.post("/tasks", json=internal_payload, headers=admin_acme_headers)
        assert res_int.status_code == 200
        int_task = res_int.json()
        assert int_task["title"] == "Internal Server Migrations"
        assert int_task["is_internal"] is True

    def test_create_task_as_member_self_assign(self, client, member_acme_headers, sample_entities, sarah_user_id):
        proj_id = sample_entities["project"]["id"]
        payload = {
            "project_id": proj_id,
            "title": "Sarah Self Assigned Task",
            "status": "todo",
            "priority": "medium",
            "assignee_id": sarah_user_id,
            "is_internal": False,
        }
        res = client.post("/tasks", json=payload, headers=member_acme_headers)
        assert res.status_code == 200
        assert res.json()["assignee_id"] == sarah_user_id

    def test_create_task_as_member_assigning_other_forbidden(
        self, client, admin_acme_headers, member_acme_headers, sample_entities, alex_user_id
    ):
        proj_id = sample_entities["project"]["id"]

        # Case A: Assignee not yet on project -> 400 Bad Request
        res_not_member = client.post(
            "/tasks",
            json={
                "project_id": proj_id,
                "title": "Sarah Assigns Alex Before Alex is Project Member",
                "status": "todo",
                "assignee_id": alex_user_id,
            },
            headers=member_acme_headers
        )
        assert res_not_member.status_code == 400
        assert "Assignee must be assigned to this project" in res_not_member.json().get("detail", "")

        # Case B: Assignee IS on the project, but Sarah tries to assign to someone else -> 403
        # Admin creates a task assigning Alex, which automatically puts Alex into project_members
        admin_task = client.post(
            "/tasks",
            json={
                "project_id": proj_id,
                "title": "Admin Task for Alex",
                "assignee_id": alex_user_id,
            },
            headers=admin_acme_headers
        )
        assert admin_task.status_code == 200

        # Now Alex is in project_members. When Sarah attempts to assign to Alex, it raises 403
        res_forbidden = client.post(
            "/tasks",
            json={
                "project_id": proj_id,
                "title": "Sarah Assigns Alex Now That Alex Is On Project",
                "assignee_id": alex_user_id,
            },
            headers=member_acme_headers
        )
        assert res_forbidden.status_code == 403
        assert "Members may only assign tasks to themselves" in res_forbidden.json().get("detail", "")



    def test_create_task_as_client_forbidden(self, client, client_acme_headers, sample_entities):
        proj_id = sample_entities["project"]["id"]
        payload = {
            "project_id": proj_id,
            "title": "Client Created Task",
            "status": "todo",
        }
        res = client.post("/tasks", json=payload, headers=client_acme_headers)
        assert res.status_code == 403
        assert "Client users cannot create tasks" in res.json().get("detail", "")

    def test_create_task_validation_errors(self, client, admin_acme_headers, sample_entities):
        proj_id = sample_entities["project"]["id"]

        # Missing / empty title
        res = client.post("/tasks", json={"project_id": proj_id, "title": ""}, headers=admin_acme_headers)
        assert res.status_code == 400

        # Title > 240 chars
        res = client.post("/tasks", json={"project_id": proj_id, "title": "A" * 241}, headers=admin_acme_headers)
        assert res.status_code == 400

        # Invalid status
        res = client.post("/tasks", json={"project_id": proj_id, "title": "Task", "status": "completed"}, headers=admin_acme_headers)
        assert res.status_code == 400

        # Invalid priority
        res = client.post("/tasks", json={"project_id": proj_id, "title": "Task", "priority": "critical"}, headers=admin_acme_headers)
        assert res.status_code == 400

        # Invalid due date
        res = client.post("/tasks", json={"project_id": proj_id, "title": "Task", "due_date": "not-a-date"}, headers=admin_acme_headers)
        assert res.status_code == 400

        # Non-boolean is_internal
        res = client.post("/tasks", json={"project_id": proj_id, "title": "Task", "is_internal": "yes"}, headers=admin_acme_headers)
        assert res.status_code == 400

        # Nonexistent project
        res = client.post("/tasks", json={"project_id": str(uuid.uuid4()), "title": "Task"}, headers=admin_acme_headers)
        assert res.status_code == 404

        # Malformed project_id
        res = client.post("/tasks", json={"project_id": "invalid-uuid", "title": "Task"}, headers=admin_acme_headers)
        assert res.status_code == 400

    def test_update_task_status_as_staff(self, client, admin_acme_headers, sample_entities):
        task_id = sample_entities["public_task"]["id"]

        for next_status in ["in_progress", "review", "done", "todo"]:
            res = client.patch(f"/tasks/{task_id}/status", json={"status": next_status}, headers=admin_acme_headers)
            assert res.status_code == 200
            assert res.json()["status"] == next_status

    def test_update_task_status_as_client_forbidden(self, client, client_acme_headers, sample_entities):
        task_id = sample_entities["public_task"]["id"]
        res = client.patch(f"/tasks/{task_id}/status", json={"status": "done"}, headers=client_acme_headers)
        assert res.status_code == 403
        assert "Client users cannot change task status" in res.json().get("detail", "")

    def test_update_task_status_validation_errors(self, client, admin_acme_headers, sample_entities):
        task_id = sample_entities["public_task"]["id"]

        # Invalid status string
        res = client.patch(f"/tasks/{task_id}/status", json={"status": "archived"}, headers=admin_acme_headers)
        assert res.status_code == 400

        # Malformed task ID
        res = client.patch("/tasks/not-a-uuid/status", json={"status": "done"}, headers=admin_acme_headers)
        assert res.status_code == 400

        # Nonexistent task ID
        res = client.patch(f"/tasks/{uuid.uuid4()}/status", json={"status": "done"}, headers=admin_acme_headers)
        assert res.status_code == 404

    def test_update_task_visibility_as_staff(self, client, admin_acme_headers, sample_entities):
        task_id = sample_entities["public_task"]["id"]

        # Staff can toggle to internal
        res = client.patch(f"/tasks/{task_id}/visibility", json={"is_internal": True}, headers=admin_acme_headers)
        assert res.status_code == 200
        assert res.json()["is_internal"] is True

        # Staff can toggle back to client-visible
        res = client.patch(f"/tasks/{task_id}/visibility", json={"is_internal": False}, headers=admin_acme_headers)
        assert res.status_code == 200
        assert res.json()["is_internal"] is False

    def test_update_task_visibility_as_client_forbidden(self, client, client_acme_headers, sample_entities):
        task_id = sample_entities["public_task"]["id"]
        res = client.patch(f"/tasks/{task_id}/visibility", json={"is_internal": True}, headers=client_acme_headers)
        assert res.status_code == 403
        assert "Client users cannot change task visibility" in res.json().get("detail", "")

    def test_task_visibility_toggle_cascades_to_children(self, client, admin_acme_headers, sample_entities):
        project_id = sample_entities["project"]["id"]

        # Create a new public task
        task_res = client.post(
            "/tasks",
            headers=admin_acme_headers,
            json={"project_id": project_id, "title": "Cascading Visibility Task", "is_internal": False}
        )
        assert task_res.status_code == 200
        task_id = task_res.json()["id"]

        # Add a public comment
        comm_res = client.post(
            f"/tasks/{task_id}/comments",
            headers=admin_acme_headers,
            json={"content": "Public comment initially", "is_internal": False}
        )
        assert comm_res.status_code == 200
        assert comm_res.json()["is_internal"] is False

        # Add a public file
        file_res = client.post(
            f"/tasks/{task_id}/files",
            headers=admin_acme_headers,
            json={"file_name": "public_doc.pdf", "file_url": "https://example.com/doc.pdf", "is_internal": False}
        )
        assert file_res.status_code == 200
        assert file_res.json()["is_internal"] is False

        # Flip task to internal
        vis_res = client.patch(
            f"/tasks/{task_id}/visibility",
            headers=admin_acme_headers,
            json={"is_internal": True}
        )
        assert vis_res.status_code == 200
        assert vis_res.json()["is_internal"] is True

        # Verify child comments and files were cascaded to internal
        comments = client.get(f"/tasks/{task_id}/comments", headers=admin_acme_headers).json()["comments"]
        assert all(c["is_internal"] is True for c in comments)

        files = client.get(f"/tasks/{task_id}/files", headers=admin_acme_headers).json()["files"]
        assert all(f["is_internal"] is True for f in files)
