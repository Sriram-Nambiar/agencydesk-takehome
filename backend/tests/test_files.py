import uuid
import pytest


class TestFiles:
    def test_list_files_as_staff_sees_all(self, client, admin_acme_headers, sample_entities):
        int_task_id = sample_entities["internal_task"]["id"]
        res = client.get(f"/tasks/{int_task_id}/files", headers=admin_acme_headers)
        assert res.status_code == 200
        files = res.json()["files"]
        assert len(files) >= 1
        assert any(f["file_name"] == "internal_schema_notes.pdf" for f in files)

    def test_list_files_as_client_leak_shield(
        self, client, admin_acme_headers, client_acme_headers, sample_entities
    ):
        pub_task_id = sample_entities["public_task"]["id"]

        # Staff uploads an internal file to the public task
        add_internal = client.post(
            f"/tasks/{pub_task_id}/files",
            json={
                "file_name": "internal_private_spec.pdf",
                "file_url": "https://example.com/files/spec.pdf",
                "is_internal": True,
            },
            headers=admin_acme_headers,
        )
        assert add_internal.status_code == 200

        # Client queries files
        client_res = client.get(f"/tasks/{pub_task_id}/files", headers=client_acme_headers)
        assert client_res.status_code == 200
        files = client_res.json()["files"]

        # Client sees public file
        assert any(f["file_name"] == "homepage_v1.pdf" for f in files)
        # Client NEVER sees internal file
        assert not any(f["file_name"] == "internal_private_spec.pdf" for f in files)
        for f in files:
            assert f["is_internal"] is False

    def test_client_access_internal_task_files_returns_404(
        self, client, client_acme_headers, sample_entities
    ):
        int_task_id = sample_entities["internal_task"]["id"]
        res = client.get(f"/tasks/{int_task_id}/files", headers=client_acme_headers)
        assert res.status_code == 404

    def test_upload_file_as_staff(self, client, member_acme_headers, sample_entities):
        pub_task_id = sample_entities["public_task"]["id"]
        payload = {
            "file_name": "banner_mockup_v2.png",
            "file_url": "https://cdn.example.com/mockups/banner_v2.png",
            "is_internal": False,
        }
        res = client.post(f"/tasks/{pub_task_id}/files", json=payload, headers=member_acme_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["file_name"] == payload["file_name"]
        assert data["approval_status"] == "pending"
        assert data["is_internal"] is False

    def test_upload_file_as_client_forbidden(self, client, client_acme_headers, sample_entities):
        pub_task_id = sample_entities["public_task"]["id"]
        payload = {
            "file_name": "client_upload.png",
            "file_url": "https://cdn.example.com/client.png",
        }
        res = client.post(f"/tasks/{pub_task_id}/files", json=payload, headers=client_acme_headers)
        assert res.status_code == 403
        assert "Clients cannot upload files" in res.json().get("detail", "")

    def test_upload_file_validation_errors(self, client, admin_acme_headers, sample_entities):
        pub_task_id = sample_entities["public_task"]["id"]

        # Missing file_name
        res = client.post(
            f"/tasks/{pub_task_id}/files",
            json={"file_name": "", "file_url": "https://example.com/test.pdf"},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

        # Invalid URL scheme
        res = client.post(
            f"/tasks/{pub_task_id}/files",
            json={"file_name": "test.pdf", "file_url": "ftp://example.com/test.pdf"},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

        # Nonexistent task ID
        res = client.post(
            f"/tasks/{uuid.uuid4()}/files",
            json={"file_name": "test.pdf", "file_url": "https://example.com/test.pdf"},
            headers=admin_acme_headers,
        )
        assert res.status_code == 404

    def test_file_approval_by_client_and_admin(
        self, client, admin_acme_headers, client_acme_headers, member_acme_headers, sample_entities
    ):
        pub_task_id = sample_entities["public_task"]["id"]

        # 1. Staff uploads a fresh deliverable for review
        upload_res = client.post(
            f"/tasks/{pub_task_id}/files",
            json={
                "file_name": "logo_final_approval.svg",
                "file_url": "https://cdn.example.com/logo.svg",
                "is_internal": False,
            },
            headers=admin_acme_headers,
        )
        assert upload_res.status_code == 200
        file_id = upload_res.json()["id"]

        # 2. Member tries to approve -> 403 (Only clients and admins can approve)
        member_try = client.patch(
            f"/files/{file_id}/approval",
            json={"approval_status": "approved"},
            headers=member_acme_headers,
        )
        assert member_try.status_code == 403
        assert "Only clients and agency admins can approve files" in member_try.json().get("detail", "")

        # 3. Client requests changes -> 200
        client_changes = client.patch(
            f"/files/{file_id}/approval",
            json={"approval_status": "needs_changes"},
            headers=client_acme_headers,
        )
        assert client_changes.status_code == 200
        assert client_changes.json()["approval_status"] == "needs_changes"

        # 4. Client approves -> 200
        client_approve = client.patch(
            f"/files/{file_id}/approval",
            json={"approval_status": "approved"},
            headers=client_acme_headers,
        )
        assert client_approve.status_code == 200
        assert client_approve.json()["approval_status"] == "approved"

    def test_client_approve_internal_file_returns_404(
        self, client, admin_acme_headers, client_acme_headers, sample_entities
    ):
        int_task_id = sample_entities["internal_task"]["id"]
        files_res = client.get(f"/tasks/{int_task_id}/files", headers=admin_acme_headers)
        int_file = next(f for f in files_res.json()["files"] if f["is_internal"])

        # Client attempt to approve internal file -> 404 (strictly shielded)
        res = client.patch(
            f"/files/{int_file['id']}/approval",
            json={"approval_status": "approved"},
            headers=client_acme_headers,
        )
        assert res.status_code == 404

    def test_admin_can_approve_internal_file(
        self, client, admin_acme_headers, sample_entities
    ):
        int_task_id = sample_entities["internal_task"]["id"]
        files_res = client.get(f"/tasks/{int_task_id}/files", headers=admin_acme_headers)
        int_file = next(f for f in files_res.json()["files"] if f["is_internal"])

        # Admin can approve internal review deliverables -> 200
        res = client.patch(
            f"/files/{int_file['id']}/approval",
            json={"approval_status": "approved"},
            headers=admin_acme_headers,
        )
        assert res.status_code == 200
        assert res.json()["approval_status"] == "approved"

    def test_approve_file_validation_errors(self, client, admin_acme_headers, sample_entities):
        pub_task_id = sample_entities["public_task"]["id"]
        files_res = client.get(f"/tasks/{pub_task_id}/files", headers=admin_acme_headers)
        pub_file = files_res.json()["files"][0]

        # Invalid status choice (not 'approved' or 'needs_changes')
        res = client.patch(
            f"/files/{pub_file['id']}/approval",
            json={"approval_status": "rejected"},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

        # Malformed UUID
        res = client.patch(
            "/files/bad-uuid/approval",
            json={"approval_status": "approved"},
            headers=admin_acme_headers,
        )
        assert res.status_code == 400

    def test_upload_file_multipart_success(
        self, client, member_acme_headers, client_acme_headers, sample_entities
    ):
        pub_task_id = sample_entities["public_task"]["id"]
        file_content = b"%PDF-1.4 Mock Deliverable File Content"
        files = {"file": ("mock_design_spec.pdf", file_content, "application/pdf")}
        data = {"is_internal": "false"}

        res = client.post(
            f"/tasks/{pub_task_id}/files/upload",
            files=files,
            data=data,
            headers=member_acme_headers,
        )
        assert res.status_code == 200
        file_data = res.json()
        assert file_data["file_name"] == "mock_design_spec.pdf"
        assert file_data["file_url"].startswith("/uploads/")
        assert file_data["is_internal"] is False
        assert file_data["approval_status"] == "pending"

        # Stored files require authenticated, tenant-scoped download access.
        download_res = client.get(f"/files/{file_data['id']}/download", headers=member_acme_headers)
        assert download_res.status_code == 200
        assert download_res.content == file_content

        public_download = client.get(f"/files/{file_data['id']}/download", headers=client_acme_headers)
        assert public_download.status_code == 200

        internal_task_id = sample_entities["internal_task"]["id"]
        internal_upload = client.post(
            f"/tasks/{internal_task_id}/files/upload",
            files={"file": ("secret.pdf", b"secret bytes", "application/pdf")},
            headers=member_acme_headers,
        )
        assert internal_upload.status_code == 200
        internal_download = client.get(
            f"/files/{internal_upload.json()['id']}/download", headers=client_acme_headers
        )
        assert internal_download.status_code == 404

        unauthenticated = client.get(f"/files/{file_data['id']}/download")
        assert unauthenticated.status_code == 401
        static_download = client.get(file_data["file_url"])
        assert static_download.status_code == 404

    def test_upload_file_multipart_as_client_forbidden(
        self, client, client_acme_headers, sample_entities
    ):
        pub_task_id = sample_entities["public_task"]["id"]
        files = {"file": ("client_attempt.pdf", b"content", "application/pdf")}
        res = client.post(
            f"/tasks/{pub_task_id}/files/upload",
            files=files,
            headers=client_acme_headers,
        )
        assert res.status_code == 403
        assert "Clients cannot upload files" in res.json().get("detail", "")

    def test_multipart_upload_rejects_unsupported_extension(self, client, member_acme_headers, sample_entities):
        response = client.post(
            f"/tasks/{sample_entities['public_task']['id']}/files/upload",
            files={"file": ("payload.html", b"<script>alert(1)</script>", "text/html")},
            headers=member_acme_headers,
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Unsupported file type"

    def test_multipart_upload_rejects_oversized_file(self, client, member_acme_headers, sample_entities):
        from config import get_settings

        max_bytes = get_settings().UPLOAD_MAX_BYTES
        response = client.post(
            f"/tasks/{sample_entities['public_task']['id']}/files/upload",
            files={"file": ("too-large.pdf", b"x" * (max_bytes + 1), "application/pdf")},
            headers=member_acme_headers,
        )
        assert response.status_code == 413

    def test_upload_file_multipart_inherits_internal_status(
        self, client, admin_acme_headers, sample_entities
    ):
        int_task_id = sample_entities["internal_task"]["id"]
        files = {"file": ("internal_blueprint.pdf", b"internal blueprint bytes", "application/pdf")}
        data = {"is_internal": "false"}  # Even if marked false, should inherit task's internal status

        res = client.post(
            f"/tasks/{int_task_id}/files/upload",
            files=files,
            data=data,
            headers=admin_acme_headers,
        )
        assert res.status_code == 200
        assert res.json()["is_internal"] is True
