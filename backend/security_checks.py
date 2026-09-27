"""HTTP smoke checks for the seeded tenant and client visibility boundaries."""
import os
import sys
import urllib.error
import urllib.request
import json

BASE = os.getenv("API_URL", "http://localhost:8000")
_client = None


def _get_inprocess_client():
    global _client
    if _client is None:
        sys.path.insert(0, os.path.dirname(__file__))
        from main import app
        from fastapi.testclient import TestClient
        _client = TestClient(app)
    return _client


def request(path, email, password="password123", agency=None, method="GET", body=None):
    try:
        login_req = urllib.request.Request(
            BASE + "/auth/login", data=json.dumps({"email": email, "password": password}).encode(),
            headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(login_req, timeout=2.0) as response:
            token = json.loads(response.read())["token"]
        headers = {"Authorization": f"Bearer {token}"}
        if agency:
            headers["X-Agency-ID"] = agency
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=2.0) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read())
        except Exception:
            payload = {}
        return error.code, payload
    except urllib.error.URLError:
        # Fall back to in-process TestClient when local server process is not actively bound
        tc = _get_inprocess_client()
        login_res = tc.post("/auth/login", json={"email": email, "password": password})
        if login_res.status_code != 200:
            return login_res.status_code, login_res.json()
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        if agency:
            headers["X-Agency-ID"] = agency
        res = tc.request(method, path, headers=headers, json=body if body is not None else None)
        try:
            return res.status_code, res.json()
        except Exception:
            return res.status_code, {}


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print("PASS", message)


def main():
    _, memberships = request("/auth/memberships", "alex@example.com")
    # membership endpoint returns an object containing agency IDs; infer sample tenants
    rows = memberships["memberships"]
    acme = next(row["agency_id"] for row in rows if row["agency_name"] == "Acme Digital Agency")
    beta = next(row["agency_id"] for row in rows if row["agency_name"] == "Beta Media Group")
    check(len(rows) == 2, "one identity can hold separate roles in two agencies")
    status, _ = request("/projects", "alex@example.com", agency="invalid-agency-id")
    check(status == 400, "malformed tenant IDs are rejected cleanly")
    status, _ = request("/projects/not-a-uuid", "alex@example.com", agency=acme)
    check(status == 400, "malformed resource IDs are rejected cleanly")

    _, acme_projects = request("/projects", "alex@example.com", agency=acme)
    _, beta_projects = request("/portal/projects", "alex@example.com", agency=beta)
    acme_project = next(p for p in acme_projects["projects"] if p["name"] == "Website Redesign")
    beta_project = next(p for p in beta_projects["projects"] if p["name"] == "Spring Campaign")
    status, _ = request(f"/projects/{beta_project['id']}", "alex@example.com", agency=acme)
    check(status == 404, "cross-tenant project ID is not readable")
    _, beta_detail = request(f"/portal/projects/{beta_project['id']}", "alex@example.com", agency=beta)
    if beta_detail["tasks"]:
        status, _ = request(f"/tasks/{beta_detail['tasks'][0]['id']}/comments", "alex@example.com", agency=acme)
        check(status == 404, "cross-tenant task child endpoints are not readable")

    _, client_projects = request("/portal/projects", "john@starlight.com", agency=acme)
    client_project = next(p for p in client_projects["projects"] if p["id"] == acme_project["id"])
    check(all(p["client_id"] == client_project["client_id"] for p in client_projects["projects"]), "client sees only its own projects")
    status, _ = request("/agency/members", "john@starlight.com", agency=acme)
    check(status == 403, "client cannot browse the agency staff directory")
    _, detail = request(f"/portal/projects/{client_project['id']}", "john@starlight.com", agency=acme)
    check(all(not task.get("is_internal", False) for task in detail["tasks"]), "portal project detail filters internal tasks")
    visible_task = detail["tasks"][0]
    _, comments = request(f"/tasks/{visible_task['id']}/comments", "john@starlight.com", agency=acme)
    check(all(not comment["is_internal"] for comment in comments["comments"]), "client comment endpoint excludes internal notes")
    _, files = request(f"/tasks/{visible_task['id']}/files", "john@starlight.com", agency=acme)
    check(all(not item["is_internal"] for item in files["files"]), "client file endpoint excludes internal files")

    status, _ = request("/tasks", "john@starlight.com", agency=acme, method="POST", body={"project_id": client_project["id"], "title": "not allowed"})
    check(status == 403, "client cannot create tasks")
    internal = next(t for t in acme_projects["projects"] if t["id"] == acme_project["id"])
    _, agency_detail = request(f"/projects/{acme_project['id']}", "alex@example.com", agency=acme)
    private_task = next(task for task in agency_detail["tasks"] if task["is_internal"])
    for suffix in ("comments", "files"):
        status, _ = request(f"/tasks/{private_task['id']}/{suffix}", "john@starlight.com", agency=acme)
        check(status == 404, f"client cannot access internal task {suffix}")
    status, _ = request(f"/tasks/{private_task['id']}/status", "john@starlight.com", agency=acme, method="PATCH", body={"status": "done"})
    check(status == 403, "client cannot change task status")

    _, member_projects = request("/projects", "sarah@acme.com", agency=acme)
    check(all(p["id"] == acme_project["id"] for p in member_projects["projects"]), "member sees assigned projects only")
    status, _ = request(f"/projects/{beta_project['id']}", "sarah@acme.com", agency=acme)
    check(status == 404, "member cannot guess an unassigned project ID")

    _, staff = request("/agency/members", "alex@example.com", agency=acme)
    sarah_id = next(person["id"] for person in staff["members"] if person["email"] == "sarah@acme.com")
    try:
        status, _ = request(f"/projects/{acme_project['id']}/members/{sarah_id}", "alex@example.com", agency=acme, method="DELETE")
        check(status == 200, "admin can revoke project membership")
        _, revoked_projects = request("/projects", "sarah@acme.com", agency=acme)
        check(not revoked_projects["projects"], "removed member loses project access immediately")
        _, retained = request(f"/projects/{acme_project['id']}", "alex@example.com", agency=acme)
        check(any(task.get("assignee_id") == sarah_id for task in retained["tasks"]), "revoking membership preserves assigned task history")
    finally:
        status, _ = request(f"/projects/{acme_project['id']}/members/{sarah_id}", "alex@example.com", agency=acme, method="PUT")
        check(status == 200, "admin can restore project membership after the check")

    status, _ = request(f"/projects/{acme_project['id']}/members/{'00000000-0000-0000-0000-000000000000'}", "alex@example.com", agency=acme, method="DELETE")
    check(status == 404, "removing a non-member is safe and does not mutate another tenant")

    status, first = request("/agency/invites", "alex@example.com", agency=acme, method="POST", body={"email": "sarah@acme.com", "role": "agency_member"})
    check(status == 200, "agency admin can invite an existing global identity")
    status, resent = request("/agency/invites", "alex@example.com", agency=acme, method="POST", body={"email": "SARAH@acme.com", "role": "agency_member"})
    check(status == 200 and first["invite"]["id"] == resent["invite"]["id"], "invite resend updates one pending invite case-insensitively")
    token = resent["invite"]["token"]
    status, accepted = request("/invites/accept", "sarah@acme.com", method="POST", body={"token": token, "password": "password123"})
    check(status == 200, "existing identity accepts invite with its password")
    status, repeated = request("/invites/accept", "sarah@acme.com", method="POST", body={"token": token, "password": "password123"})
    check(status == 200 and accepted["user_id"] == repeated["user_id"], "accepting the same invite twice reuses one identity")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FAIL", exc, file=sys.stderr)
        raise
