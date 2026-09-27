import pytest
import psycopg2
from database import get_db, DB_HOST, DB_NAME, DB_USER, DB_PASS, DB_PORT


class TestSchemaIntegrityAndEdgeCases:
    def test_schema_enforces_project_member_same_agency(self, agencies):
        """
        Schema Verification:
        The database schema itself rejects assigning a user to a project if the user
        is not a member of the project's agency (via composite foreign keys).
        """
        conn = psycopg2.connect(
            host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS, port=DB_PORT
        )
        cur = conn.cursor()
        try:
            # Sarah Chen is member in Acme, not Beta
            cur.execute("SELECT id FROM users WHERE email = 'sarah@acme.com'")
            sarah_id = cur.fetchone()[0]

            # Fetch a project belonging to Beta Media Group
            cur.execute("SELECT id FROM projects WHERE agency_id = %s LIMIT 1", (agencies["beta"],))
            beta_project_id = cur.fetchone()[0]

            # Attempt to add Sarah directly to Beta's project in SQL
            with pytest.raises(psycopg2.IntegrityError) as exc_info:
                cur.execute(
                    "INSERT INTO project_members (project_id, user_id) VALUES (%s, %s)",
                    (beta_project_id, sarah_id)
                )
                conn.commit()

            assert "pm_user_same_agency" in str(exc_info.value)
        finally:
            conn.rollback()
            cur.close()
            conn.close()

    def test_internal_task_forces_comments_and_files_internal(
        self, client, admin_acme_headers, sample_entities
    ):
        """
        Edge Case & Leak Shield:
        Any comments or files added to an internal task must strictly inherit internal status,
        preventing accidental leakage if queried independently.
        """
        project_id = sample_entities["project"]["id"]

        # 1. Create an internal task
        task_res = client.post(
            "/tasks",
            headers=admin_acme_headers,
            json={
                "project_id": project_id,
                "title": "Private Internal Review",
                "is_internal": True,
            }
        )
        assert task_res.status_code == 200
        task_id = task_res.json()["id"]

        # 2. Add comment with is_internal=False on an internal task
        comm_res = client.post(
            f"/tasks/{task_id}/comments",
            headers=admin_acme_headers,
            json={"content": "Notes for internal review", "is_internal": False}
        )
        assert comm_res.status_code == 200
        assert comm_res.json()["is_internal"] is True, "Comment on internal task must be forced internal"

        # 3. Upload file with is_internal=False on an internal task
        file_res = client.post(
            f"/tasks/{task_id}/files",
            headers=admin_acme_headers,
            json={
                "file_name": "internal_memo.pdf",
                "file_url": "https://example.com/memo.pdf",
                "is_internal": False,
            }
        )
        assert file_res.status_code == 200
        assert file_res.json()["is_internal"] is True, "File on internal task must be forced internal"

    def test_project_dashboards_task_counts_scoped_to_viewer(
        self, client, admin_acme_headers, client_acme_headers, sample_entities
    ):
        """
        Dashboard & Reporting:
        Both agency and client project views provide task_counts_by_status,
        scoped to what the viewer is allowed to see.
        """
        project_id = sample_entities["project"]["id"]

        # 1. Agency dashboard
        agency_res = client.get(f"/projects/{project_id}", headers=admin_acme_headers)
        assert agency_res.status_code == 200
        agency_data = agency_res.json()
        assert "task_counts_by_status" in agency_data
        assert "total_hours_logged" in agency_data
        assert isinstance(agency_data["task_counts_by_status"], dict)
        assert "todo" in agency_data["task_counts_by_status"]

        # 2. Client dashboard
        client_res = client.get(f"/portal/projects/{project_id}", headers=client_acme_headers)
        assert client_res.status_code == 200
        client_data = client_res.json()
        assert "task_counts_by_status" in client_data
        assert "total_hours_logged" not in client_data  # Staff hours must never leak to client
        assert isinstance(client_data["task_counts_by_status"], dict)
