import uuid
import pytest


class TestComments:
    def test_list_comments_as_staff_sees_all(self, client, admin_acme_headers, sample_entities):
        int_task_id = sample_entities["internal_task"]["id"]
        res = client.get(f"/tasks/{int_task_id}/comments", headers=admin_acme_headers)
        assert res.status_code == 200
        comments = res.json()["comments"]
        assert len(comments) >= 1
        # Staff can see internal comments
        assert any(c["is_internal"] is True for c in comments)

    def test_list_comments_as_client_leak_shield(
        self, client, admin_acme_headers, client_acme_headers, sample_entities
    ):
        pub_task_id = sample_entities["public_task"]["id"]

        # Staff adds an internal comment to the public task
        add_internal = client.post(
            f"/tasks/{pub_task_id}/comments",
            json={"content": "Private staff note on public task", "is_internal": True},
            headers=admin_acme_headers,
        )
        assert add_internal.status_code == 200

        # Staff adds a public comment
        add_public = client.post(
            f"/tasks/{pub_task_id}/comments",
            json={"content": "Visible comment to client", "is_internal": False},
            headers=admin_acme_headers,
        )
        assert add_public.status_code == 200

        # Client queries comments
        client_res = client.get(f"/tasks/{pub_task_id}/comments", headers=client_acme_headers)
        assert client_res.status_code == 200
        client_comments = client_res.json()["comments"]

        # Leak Shield assertion: zero internal comments returned to client
        for c in client_comments:
            assert c["is_internal"] is False
            assert "Private staff note" not in c["content"]

        assert any("Visible comment to client" in c["content"] for c in client_comments)

    def test_client_access_internal_task_comments_returns_404(
        self, client, client_acme_headers, sample_entities
    ):
        int_task_id = sample_entities["internal_task"]["id"]
        res = client.get(f"/tasks/{int_task_id}/comments", headers=client_acme_headers)
        assert res.status_code == 404

    def test_create_comment_as_staff(self, client, member_acme_headers, sample_entities):
        pub_task_id = sample_entities["public_task"]["id"]
        res = client.post(
            f"/tasks/{pub_task_id}/comments",
            json={"content": "Member note on public task", "is_internal": True},
            headers=member_acme_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["content"] == "Member note on public task"
        assert data["is_internal"] is True

    def test_create_comment_as_client_forced_to_public(
        self, client, client_acme_headers, sample_entities
    ):
        pub_task_id = sample_entities["public_task"]["id"]
        # Client tries to pass is_internal=True
        res = client.post(
            f"/tasks/{pub_task_id}/comments",
            json={"content": "Client feedback here", "is_internal": True},
            headers=client_acme_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["content"] == "Client feedback here"
        # Backend MUST force is_internal to False for clients
        assert data["is_internal"] is False

    def test_client_post_comment_on_internal_task_returns_404(
        self, client, client_acme_headers, sample_entities
    ):
        int_task_id = sample_entities["internal_task"]["id"]
        res = client.post(
            f"/tasks/{int_task_id}/comments",
            json={"content": "Sneak comment", "is_internal": False},
            headers=client_acme_headers,
        )
        assert res.status_code == 404

    def test_create_comment_validation_errors(self, client, admin_acme_headers, sample_entities):
        pub_task_id = sample_entities["public_task"]["id"]

        # Empty content
        res = client.post(
            f"/tasks/{pub_task_id}/comments",
            json={"content": "   "},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

        # Content too long (> 5000 characters)
        res = client.post(
            f"/tasks/{pub_task_id}/comments",
            json={"content": "X" * 5001},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

        # Non-boolean is_internal
        res = client.post(
            f"/tasks/{pub_task_id}/comments",
            json={"content": "Hello", "is_internal": "invalid"},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

        # Nonexistent task ID
        res = client.post(
            f"/tasks/{uuid.uuid4()}/comments",
            json={"content": "Hello"},
            headers=admin_acme_headers,
        )
        assert res.status_code == 404

        # Malformed UUID
        res = client.post(
            "/tasks/not-a-uuid/comments",
            json={"content": "Hello"},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400
