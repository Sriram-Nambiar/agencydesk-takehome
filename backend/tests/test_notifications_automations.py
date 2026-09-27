import pytest
from redis_client import ping_redis, get_redis


class TestNotificationsAndAutomations:
    def test_redis_connection_live(self):
        """Verify Redis is reachable."""
        assert ping_redis() is True

    def test_get_notifications_and_unread_count(self, client, admin_acme_headers):
        """Test retrieving notifications for authenticated user."""
        res = client.get("/notifications", headers=admin_acme_headers)
        assert res.status_code == 200
        data = res.json()
        assert "notifications" in data
        assert "unread_count" in data
        assert isinstance(data["notifications"], list)

    def test_cached_unread_count_endpoint(self, client, admin_acme_headers):
        """Test the rapid cached unread-count endpoint."""
        # First call populates cache
        res1 = client.get("/notifications/unread-count", headers=admin_acme_headers)
        assert res1.status_code == 200
        count1 = res1.json()["unread_count"]

        # Second call hits Redis cache
        res2 = client.get("/notifications/unread-count", headers=admin_acme_headers)
        assert res2.status_code == 200
        assert res2.json()["unread_count"] == count1

    def test_unread_count_cache_does_not_bypass_membership(self, client, client_acme_headers, agencies):
        """A cached count must not grant access to an agency without membership."""
        user_id = client.get(
            "/auth/me", headers={"Authorization": client_acme_headers["Authorization"]}
        ).json()["id"]
        beta_id = agencies["beta"]
        assert get_redis().set(f"agencydesk:unread:{beta_id}:{user_id}", 99, ex=300)

        headers = {**client_acme_headers, "X-Agency-ID": beta_id}
        response = client.get("/notifications/unread-count", headers=headers)
        assert response.status_code == 403

    def test_mark_notification_as_read_and_read_all(self, client, member_acme_headers):
        """Test marking a single notification as read and read-all."""
        res = client.get("/notifications", headers=member_acme_headers)
        assert res.status_code == 200
        notifs = res.json()["notifications"]

        if notifs:
            notif_id = notifs[0]["id"]
            patch_res = client.patch(f"/notifications/{notif_id}/read", headers=member_acme_headers)
            assert patch_res.status_code == 200
            assert patch_res.json()["is_read"] is True

        read_all_res = client.post("/notifications/read-all", headers=member_acme_headers)
        assert read_all_res.status_code == 200
        assert read_all_res.json()["success"] is True

        # Unread count should now be 0
        count_res = client.get("/notifications/unread-count", headers=member_acme_headers)
        assert count_res.json()["unread_count"] == 0

    def test_client_cannot_access_automations(self, client, client_acme_headers):
        """Security: Client users cannot view or manipulate agency automations."""
        res = client.get("/automations", headers=client_acme_headers)
        assert res.status_code == 403
        assert "Client users cannot view" in res.json()["detail"]

        create_res = client.post(
            "/automations",
            headers=client_acme_headers,
            json={
                "name": "Malicious rule",
                "trigger_event": "file_needs_changes",
                "action_type": "update_task_status",
                "action_config": {"target_status": "done"},
            }
        )
        assert create_res.status_code == 403

    def test_agency_admin_can_manage_automations(self, client, admin_acme_headers):
        """Admin can list, create, toggle, and delete automations."""
        # 1. List
        list_res = client.get("/automations", headers=admin_acme_headers)
        assert list_res.status_code == 200
        automations = list_res.json()["automations"]
        assert len(automations) >= 1

        # 2. Create new rule
        create_res = client.post(
            "/automations",
            headers=admin_acme_headers,
            json={
                "name": "Auto-notify Admin on Urgent Tasks",
                "trigger_event": "comment_created",
                "action_type": "notify_admins",
                "action_config": {},
                "is_enabled": True,
            }
        )
        assert create_res.status_code == 200
        new_auto = create_res.json()
        auto_id = new_auto["id"]
        assert new_auto["name"] == "Auto-notify Admin on Urgent Tasks"

        # 3. Patch/toggle rule
        patch_res = client.patch(
            f"/automations/{auto_id}",
            headers=admin_acme_headers,
            json={"is_enabled": False}
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["is_enabled"] is False

        # 4. Delete rule
        del_res = client.delete(f"/automations/{auto_id}", headers=admin_acme_headers)
        assert del_res.status_code == 200
        assert del_res.json()["success"] is True

    def test_automation_auto_reopens_task_when_client_requests_changes(
        self, client, admin_acme_headers, client_acme_headers
    ):
        """
        End-to-end Automation & Notification Test:
        When a client marks a file as 'needs_changes', the automation rule triggers,
        reopening the task status to 'in_progress' and dispatching a notification.
        """
        # 1. Admin creates a task and sets status to 'review'
        acme_projects = client.get("/projects", headers=admin_acme_headers).json()["projects"]
        project_id = acme_projects[0]["id"]

        task_res = client.post(
            "/tasks",
            headers=admin_acme_headers,
            json={
                "project_id": project_id,
                "title": "Automation Test Deliverable",
                "status": "review",
                "is_internal": False,
            }
        )
        assert task_res.status_code == 200
        task_id = task_res.json()["id"]

        # 2. Upload a client-visible file
        file_res = client.post(
            f"/tasks/{task_id}/files",
            headers=admin_acme_headers,
            json={
                "file_name": "deliverable_spec.pdf",
                "file_url": "https://example.com/spec.pdf",
                "is_internal": False,
            }
        )
        assert file_res.status_code == 200
        file_id = file_res.json()["id"]

        # 3. Client user marks file as 'needs_changes'
        approval_res = client.patch(
            f"/files/{file_id}/approval",
            headers=client_acme_headers,
            json={"approval_status": "needs_changes"}
        )
        assert approval_res.status_code == 200

        # 4. Verify task status was automatically reopened to 'in_progress' by the automation!
        proj_data = client.get(f"/projects/{project_id}", headers=admin_acme_headers).json()
        proj_tasks = proj_data["tasks"]
        target_task = next(t for t in proj_tasks if t["id"] == task_id)
        assert target_task["status"] == "in_progress", "Automation should have changed status to in_progress"

        # 5. Verify notification was recorded in database
        notif_res = client.get("/notifications", headers=admin_acme_headers)
        assert notif_res.status_code == 200
        notifs = notif_res.json()["notifications"]
        assert any(
            "Changes Requested" in n["title"] or "Automation" in n["title"]
            for n in notifs
        )

    def test_client_leak_shield_no_notification_for_internal_tasks(
        self, client, admin_acme_headers, client_acme_headers
    ):
        """
        Client users must NEVER receive notifications for internal (agency-only) tasks or comments.
        """
        acme_projects = client.get("/projects", headers=admin_acme_headers).json()["projects"]
        project_id = acme_projects[0]["id"]

        # Initial client notification count
        c_init = client.get("/notifications", headers=client_acme_headers).json()["unread_count"]

        # Admin creates internal task and adds internal comment
        task_res = client.post(
            "/tasks",
            headers=admin_acme_headers,
            json={
                "project_id": project_id,
                "title": "Secret Agency Strategy Discussion",
                "is_internal": True,
            }
        )
        internal_task_id = task_res.json()["id"]

        client.post(
            f"/tasks/{internal_task_id}/comments",
            headers=admin_acme_headers,
            json={
                "content": "Confidential budget discussion for agency only.",
                "is_internal": True,
            }
        )

        # Client notification count must remain completely unchanged!
        c_after = client.get("/notifications", headers=client_acme_headers).json()["unread_count"]
        assert c_after == c_init, "Client unread count must NOT change for internal events"
