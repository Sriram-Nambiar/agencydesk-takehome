import uuid
import pytest


class TestTimeTracking:
    def test_log_time_as_staff(self, client, member_acme_headers, sample_entities):
        pub_task_id = sample_entities["public_task"]["id"]
        payload = {
            "duration_minutes": 120,
            "note": "Developed and verified endpoint tests",
            "entry_date": "2026-10-18",
        }
        res = client.post(f"/tasks/{pub_task_id}/time", json=payload, headers=member_acme_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["duration_minutes"] == 120
        assert data["note"] == payload["note"]
        assert data["entry_date"] == payload["entry_date"]

    def test_get_time_entries_as_staff(self, client, admin_acme_headers, sample_entities):
        int_task_id = sample_entities["internal_task"]["id"]
        res = client.get(f"/tasks/{int_task_id}/time", headers=admin_acme_headers)
        assert res.status_code == 200
        entries = res.json()["time_entries"]
        assert len(entries) >= 1
        # In seed data, Sarah logged 180 mins
        entry = entries[0]
        assert "duration_minutes" in entry
        assert "user_name" in entry
        assert entry["user_name"] == "Sarah Chen"

    def test_client_log_time_forbidden(self, client, client_acme_headers, sample_entities):
        pub_task_id = sample_entities["public_task"]["id"]
        res = client.post(
            f"/tasks/{pub_task_id}/time",
            json={"duration_minutes": 60, "note": "Client time"},
            headers=client_acme_headers,
        )
        assert res.status_code == 403
        assert "Client users cannot log time" in res.json().get("detail", "")

    def test_client_get_time_forbidden(self, client, client_acme_headers, sample_entities):
        pub_task_id = sample_entities["public_task"]["id"]
        res = client.get(f"/tasks/{pub_task_id}/time", headers=client_acme_headers)
        assert res.status_code == 403
        assert "Client users cannot view time entries" in res.json().get("detail", "")

    def test_log_time_validation_errors(self, client, admin_acme_headers, sample_entities):
        pub_task_id = sample_entities["public_task"]["id"]

        # Duration 0
        res = client.post(
            f"/tasks/{pub_task_id}/time",
            json={"duration_minutes": 0},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

        # Duration negative
        res = client.post(
            f"/tasks/{pub_task_id}/time",
            json={"duration_minutes": -30},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

        # Duration > 1440 (exceeds 24 hours in a single entry)
        res = client.post(
            f"/tasks/{pub_task_id}/time",
            json={"duration_minutes": 1441},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

        # Non-integer duration
        res = client.post(
            f"/tasks/{pub_task_id}/time",
            json={"duration_minutes": "two hours"},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

        # Invalid entry_date format
        res = client.post(
            f"/tasks/{pub_task_id}/time",
            json={"duration_minutes": 60, "entry_date": "10-18-2026"},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

        # Nonexistent task ID
        res = client.post(
            f"/tasks/{uuid.uuid4()}/time",
            json={"duration_minutes": 60},
            headers=admin_acme_headers,
        )
        assert res.status_code == 404
