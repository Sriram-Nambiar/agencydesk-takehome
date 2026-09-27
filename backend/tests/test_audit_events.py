from database import get_db


class TestAuditEvents:
    def test_task_visibility_change_is_audited(self, client, admin_acme_headers, sample_entities):
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO tasks (agency_id, project_id, title, is_internal)
                       VALUES (%s, %s, 'Audit test visibility task', FALSE) RETURNING id""",
                    (admin_acme_headers["X-Agency-ID"], sample_entities["project"]["id"]),
                )
                task_id = str(cur.fetchone()["id"])
            conn.commit()
        finally:
            conn.close()

        try:
            response = client.patch(
                f"/tasks/{task_id}/visibility",
                headers=admin_acme_headers,
                json={"is_internal": True},
            )
            assert response.status_code == 200

            conn = get_db()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT action, entity_id, agency_id, details
                           FROM audit_events WHERE entity_id = %s AND action = 'task.visibility_changed'
                           ORDER BY created_at DESC LIMIT 1""",
                        (task_id,),
                    )
                    event = cur.fetchone()
                assert event is not None
                assert event["agency_id"] == admin_acme_headers["X-Agency-ID"]
                assert event["details"] == {"from_internal": False, "to_internal": True}
            finally:
                conn.close()

            restore_response = client.patch(
                f"/tasks/{task_id}/visibility",
                headers=admin_acme_headers,
                json={"is_internal": False},
            )
            assert restore_response.status_code == 200
        finally:
            conn = get_db()
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
                conn.commit()
            finally:
                conn.close()
