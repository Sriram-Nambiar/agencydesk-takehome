"""
Comprehensive Verification of the 5 Explicit Edge Cases from Sapyon Take-Home Specification:

1. Cross-tenant access:
   Tenant A cannot read or write Tenant B's data, even when guessing resource IDs.
2. Internal content leaking to clients:
   Strict leak-shield across projects, tasks, comments, files, directories, and status updates.
3. One person, two agencies:
   The same global user identity can be an agency_admin in Agency A and a client_user in Agency B.
4. Invite races:
   Resending an invite does not duplicate rows (idempotent); accepting twice does not duplicate accounts.
5. Removing a team member mid-task:
   Removing an assigned member unassigns incomplete tasks (assignee = NULL) while preserving completed task history.
"""

import uuid
import pytest


class TestEvaluationEdgeCases:
    # ──────────────────────────────────────────────────────────────────────────
    # Edge Case 1: Cross-Tenant Access
    # ──────────────────────────────────────────────────────────────────────────
    def test_edge_case_1_cross_tenant_access_blocked_even_with_guessed_id(
        self, client, admin_acme_headers, admin_beta_headers, member_acme_headers, agencies
    ):
        """Tenant A can't read/write Tenant B's data, even by guessing an ID."""
        # Step 1: Obtain a valid project ID belonging strictly to Tenant B (Beta)
        beta_portal = client.get("/portal/projects", headers=admin_beta_headers)
        assert beta_portal.status_code == 200
        beta_projects = beta_portal.json()["projects"]
        assert len(beta_projects) >= 1
        beta_proj_id = beta_projects[0]["id"]

        # Step 2: Tenant A (Acme admin) guesses the exact UUID of Tenant B's project -> MUST return 404
        cross_read = client.get(f"/projects/{beta_proj_id}", headers=admin_acme_headers)
        assert cross_read.status_code == 404, "Tenant A must receive 404 when querying Tenant B project"

        # Step 3: Tenant A staff tries to list or mutate tasks inside Tenant B's project -> MUST return 404
        cross_create_task = client.post(
            "/tasks",
            headers=admin_acme_headers,
            json={
                "project_id": beta_proj_id,
                "title": "Cross Tenant Intrusion Attempt",
                "status": "todo",
            },
        )
        assert cross_create_task.status_code == 404, "Cannot create tasks in another tenant's project"

        # Step 4: Tenant A staff passes Tenant B's agency ID in X-Agency-ID -> MUST return 403
        sarah_token_res = client.post("/auth/login", json={"email": "sarah@acme.com", "password": "password123"})
        sarah_token = sarah_token_res.json()["token"]
        spoofed_tenant_headers = {
            "Authorization": f"Bearer {sarah_token}",
            "X-Agency-ID": agencies["beta"],
        }
        spoof_res = client.get("/projects", headers=spoofed_tenant_headers)
        assert spoof_res.status_code == 403
        assert "Access denied to this agency tenant" in spoof_res.json().get("detail", "")

    # ──────────────────────────────────────────────────────────────────────────
    # Edge Case 2: Internal Content Leaking to Clients
    # ──────────────────────────────────────────────────────────────────────────
    def test_edge_case_2_internal_content_leak_shield_across_all_endpoints(
        self, client, admin_acme_headers, client_acme_headers, sample_entities
    ):
        """Internal content leaking to clients: check every code path (search, filters, comments, files)."""
        pub_task_id = sample_entities["public_task"]["id"]
        int_task_id = sample_entities["internal_task"]["id"]

        # 1. Project detail for client strictly excludes internal tasks
        portal_proj_res = client.get(
            f"/portal/projects/{sample_entities['project']['id']}",
            headers=client_acme_headers,
        )
        assert portal_proj_res.status_code == 200
        portal_tasks = portal_proj_res.json()["tasks"]
        for t in portal_tasks:
            assert t.get("is_internal") is not True, "Internal tasks leaked into client portal"
        assert not any(t["id"] == int_task_id for t in portal_tasks)

        # 2. Direct lookup of internal task comments by client -> 404 (strictly shielded, no existence leak)
        int_comments_res = client.get(f"/tasks/{int_task_id}/comments", headers=client_acme_headers)
        assert int_comments_res.status_code == 404

        # 3. Direct lookup of internal task files by client -> 404
        int_files_res = client.get(f"/tasks/{int_task_id}/files", headers=client_acme_headers)
        assert int_files_res.status_code == 404

        # 4. Client cannot see internal comments on a public task
        # Staff posts an internal note on the public task
        client.post(
            f"/tasks/{pub_task_id}/comments",
            headers=admin_acme_headers,
            json={"content": "Confidential Staff Discussion Note", "is_internal": True},
        )
        comments_res = client.get(f"/tasks/{pub_task_id}/comments", headers=client_acme_headers)
        assert comments_res.status_code == 200
        client_comments = comments_res.json()["comments"]
        for c in client_comments:
            assert c["is_internal"] is False
            assert "Confidential Staff Discussion Note" not in c["content"]

        # 5. Client cannot see internal files on a public task
        client.post(
            f"/tasks/{pub_task_id}/files",
            headers=admin_acme_headers,
            json={"file_name": "internal_margins.pdf", "file_url": "https://example.com/margins.pdf", "is_internal": True},
        )
        files_res = client.get(f"/tasks/{pub_task_id}/files", headers=client_acme_headers)
        assert files_res.status_code == 200
        for f in files_res.json()["files"]:
            assert f["is_internal"] is False
            assert f["file_name"] != "internal_margins.pdf"

        # 6. Client cannot mutate task status
        patch_status = client.patch(
            f"/tasks/{pub_task_id}/status",
            headers=client_acme_headers,
            json={"status": "done"},
        )
        assert patch_status.status_code == 403

        # 7. Client cannot create tasks
        create_task_res = client.post(
            "/tasks",
            headers=client_acme_headers,
            json={"project_id": sample_entities["project"]["id"], "title": "Client Created Task"},
        )
        assert create_task_res.status_code == 403

        # 8. Client cannot view agency staff directory
        staff_dir_res = client.get("/agency/members", headers=client_acme_headers)
        assert staff_dir_res.status_code == 403

        # 9. Client cannot view time logs
        time_res = client.get(f"/tasks/{pub_task_id}/time", headers=client_acme_headers)
        assert time_res.status_code == 403

    # ──────────────────────────────────────────────────────────────────────────
    # Edge Case 3: One Person, Two Agencies
    # ──────────────────────────────────────────────────────────────────────────
    def test_edge_case_3_one_person_two_agencies_with_different_roles(
        self, client, admin_token, agencies
    ):
        """The same email may be a client contact for two different agencies with different roles."""
        # Alex Rivera is seeded across two agencies:
        # Agency A (Acme): agency_admin
        # Agency B (Beta): client_user

        headers_base = {"Authorization": f"Bearer {admin_token}"}

        # 1. Single identity has multiple memberships
        mem_res = client.get("/auth/memberships", headers=headers_base)
        assert mem_res.status_code == 200
        memberships = mem_res.json()["memberships"]
        assert len(memberships) == 2

        acme_mem = next(m for m in memberships if m["agency_id"] == agencies["acme"])
        beta_mem = next(m for m in memberships if m["agency_id"] == agencies["beta"])
        assert acme_mem["role"] == "agency_admin"
        assert beta_mem["role"] == "client_user"

        # 2. Acting in Agency A context: has admin powers (can view full project management)
        acme_projects = client.get(
            "/projects",
            headers={"Authorization": f"Bearer {admin_token}", "X-Agency-ID": agencies["acme"]},
        )
        assert acme_projects.status_code == 200
        assert "projects" in acme_projects.json()

        # 3. Acting in Agency B context with the EXACT same token: behaves strictly as client_user
        beta_staff_proj = client.get(
            "/projects",
            headers={"Authorization": f"Bearer {admin_token}", "X-Agency-ID": agencies["beta"]},
        )
        assert beta_staff_proj.status_code == 403
        assert "Client users must use /portal endpoints" in beta_staff_proj.json().get("detail", "")

        beta_portal_proj = client.get(
            "/portal/projects",
            headers={"Authorization": f"Bearer {admin_token}", "X-Agency-ID": agencies["beta"]},
        )
        assert beta_portal_proj.status_code == 200
        assert "projects" in beta_portal_proj.json()

    # ──────────────────────────────────────────────────────────────────────────
    # Edge Case 4: Invite Races & Idempotency
    # ──────────────────────────────────────────────────────────────────────────
    def test_edge_case_4_invite_races_and_idempotent_acceptance(
        self, client, admin_acme_headers
    ):
        """Resending an invite shouldn't duplicate it; accepting the same invite twice shouldn't create two accounts."""
        unique_email = f"contractor_{uuid.uuid4().hex[:8]}@example.com"

        # 1. Send initial invite
        send_1 = client.post(
            "/agency/invites",
            headers=admin_acme_headers,
            json={"email": unique_email, "role": "agency_member"},
        )
        assert send_1.status_code == 200
        first_invite = send_1.json()["invite"]
        token_1 = first_invite["token"]

        # 2. Resend invite with different case (simulate double-click or resend button)
        send_2 = client.post(
            "/agency/invites",
            headers=admin_acme_headers,
            json={"email": unique_email.upper(), "role": "agency_member"},
        )
        assert send_2.status_code == 200
        second_invite = send_2.json()["invite"]

        # Idempotent: same invite row ID updated, not duplicated
        assert first_invite["id"] == second_invite["id"], "Resending an invite must not create a duplicate row"
        token_2 = second_invite["token"]

        # 3. First acceptance: creates user account & membership
        accept_1 = client.post(
            "/invites/accept",
            json={"token": token_2, "password": "securepassword123", "full_name": "New Contractor"},
        )
        assert accept_1.status_code == 200
        user_id_1 = accept_1.json()["user_id"]

        # 4. Second acceptance (simulating concurrent double click or browser reload)
        accept_2 = client.post(
            "/invites/accept",
            json={"token": token_2, "password": "securepassword123", "full_name": "New Contractor"},
        )
        assert accept_2.status_code == 200
        user_id_2 = accept_2.json()["user_id"]

        # Identical user ID reused, never duplicates user or membership
        assert user_id_1 == user_id_2, "Accepting twice must not create two accounts"

    # ──────────────────────────────────────────────────────────────────────────
    # Edge Case 5: Removing a Team Member Mid-Task
    # ──────────────────────────────────────────────────────────────────────────
    def test_edge_case_5_removing_team_member_mid_task_policy(
        self, client, admin_acme_headers, sample_entities, sarah_user_id
    ):
        """Decide what happens to tasks assigned to an agency_member removed from a project, and implement it."""
        project_id = sample_entities["project"]["id"]

        # Ensure Sarah is assigned to project
        client.put(f"/projects/{project_id}/members/{sarah_user_id}", headers=admin_acme_headers)

        # Create active in-progress task assigned to Sarah
        active_task = client.post(
            "/tasks",
            headers=admin_acme_headers,
            json={
                "project_id": project_id,
                "title": "Sarah Active Sprint Deliverable",
                "status": "in_progress",
                "assignee_id": sarah_user_id,
                "is_internal": False,
            },
        ).json()

        # Create completed done task assigned to Sarah
        done_task = client.post(
            "/tasks",
            headers=admin_acme_headers,
            json={
                "project_id": project_id,
                "title": "Sarah Historical Completed Task",
                "status": "done",
                "assignee_id": sarah_user_id,
                "is_internal": False,
            },
        ).json()

        # Policy execution: Remove Sarah with unassign_active=true
        del_res = client.delete(
            f"/projects/{project_id}/members/{sarah_user_id}?unassign_active=true",
            headers=admin_acme_headers,
        )
        assert del_res.status_code == 200
        assert del_res.json()["access"] == "removed"

        # Verify task states post-removal:
        proj_detail = client.get(f"/projects/{project_id}", headers=admin_acme_headers).json()
        tasks_map = {t["id"]: t for t in proj_detail["tasks"]}

        # 1. In-progress task is unassigned (assignee_id set to None) so work is not blocked
        assert tasks_map[active_task["id"]]["assignee_id"] is None, "Active task should be unassigned when member is removed"

        # 2. Completed task preserves Sarah's user_id as historical record for audit trail
        assert tasks_map[done_task["id"]]["assignee_id"] == sarah_user_id, "Completed task history should be preserved"

        # 3. Global user record remains intact (not deleted)
        sarah_token_res = client.post("/auth/login", json={"email": "sarah@acme.com", "password": "password123"})
        assert sarah_token_res.status_code == 200, "Global user account must never be deleted when membership is removed"

        # 4. Sarah immediately loses project access
        sarah_headers = {
            "Authorization": f"Bearer {sarah_token_res.json()['token']}",
            "X-Agency-ID": sample_entities["project"]["agency_id"],
        }
        sarah_proj_view = client.get(f"/projects/{project_id}", headers=sarah_headers)
        assert sarah_proj_view.status_code == 404, "Removed member must lose access to project immediately"

        # Cleanup: Restore Sarah to project
        client.put(f"/projects/{project_id}/members/{sarah_user_id}", headers=admin_acme_headers)
