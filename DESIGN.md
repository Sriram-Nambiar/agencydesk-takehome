# AgencyDesk — System Architecture & Design Document

A concise half-page design summary addressing the core evaluation criteria for AgencyDesk.

---

## 1. How the Schema Enforces Tenant Isolation

Rather than relying purely on application-level `WHERE agency_id = ...` clauses, AgencyDesk enforces multi-tenant boundaries directly at the PostgreSQL schema layer using **composite foreign keys**:

- **Every entity belongs to an agency**: `projects`, `tasks`, `task_comments`, `task_files`, `time_entries`, and `agency_memberships` each carry a non-null `agency_id UUID REFERENCES agencies(id) ON DELETE CASCADE`.
- **Composite Unique Constraints**: Key tables declare composite uniqueness:
  - `projects (agency_id, id)`
  - `tasks (agency_id, id)`
  - `clients (agency_id, id)`
  - `agency_memberships (user_id, agency_id)`
- **Cross-Tenant Constraint Enforcement**: Child tables link via composite foreign keys:
  ```sql
  -- Prevents tasks from referencing a project belonging to a different agency
  FOREIGN KEY (agency_id, project_id) REFERENCES projects(agency_id, id) ON DELETE CASCADE

  -- Prevents comments/files from referencing tasks of another agency
  FOREIGN KEY (agency_id, task_id) REFERENCES tasks(agency_id, id) ON DELETE CASCADE
  ```
  Even if application code suffered a bug or attempted to link Tenant A's task to Tenant B's project, PostgreSQL rejects the transaction at the database engine level.
- **Request Context**: Every request authenticates via JWT, resolves active tenant via `X-Agency-ID`, and validates non-deleted membership before executing queries. Foreign or guessed IDs return `HTTP 404` to avoid leaking resource existence.

---

## 2. How a Client is Blocked from Internal Content

AgencyDesk treats the frontend purely as a display layer; security boundaries are enforced strictly in the backend and database:

1. **Dual-Endpoint Architecture**:
   - Agency staff access `/projects` and `/projects/{id}`.
   - Client users are restricted to `/portal/projects` and `/portal/projects/{id}` (calling staff routes returns `HTTP 403 Forbidden`).
2. **Strict Query Filtering & 404 Existence Masking**:
   - In portal views, SQL queries enforce `is_internal = FALSE`.
   - If a client attempts to fetch or manipulate an internal task (`/tasks/{internal_task_id}/comments` or `/tasks/{internal_task_id}/files`), the server returns `HTTP 404 Not Found`, denying that the resource exists.
   - On public tasks with mixed comments/files, client queries include `AND is_internal = FALSE`.
3. **Write Protection**:
   - Clients cannot create tasks (`HTTP 403`).
   - Clients cannot mutate task status (`HTTP 403`).
   - Clients cannot upload files or view time tracking entries (`HTTP 403`).
   - Clients can only comment on public tasks (forced `is_internal = FALSE`) and approve/request changes on public files.
4. **Leak-Shield Cascading**:
   - When an agency admin toggles a task from public to internal (`PATCH /tasks/{id}/visibility`), the backend automatically executes an atomic cascade:
     ```sql
     UPDATE task_comments SET is_internal = TRUE WHERE task_id = %s;
     UPDATE task_files SET is_internal = TRUE WHERE task_id = %s;
     ```
     This prevents historical public comments or attached deliverables from accidentally leaking after a visibility change.

---

## 3. How the Identity Model Supports One Person Across Two Agencies

The identity model separates **authentication (who you are)** from **authorization (what role you hold per tenant)**:

```
[ users ] (Global identity: id, email [case-insensitive unique], password_hash, full_name)
    │
    ├── [ agency_memberships ] (Agency A) ── role: 'agency_admin', client_id: NULL
    │
    └── [ agency_memberships ] (Agency B) ── role: 'client_user',  client_id: UUID('client-nike')
```

- **Global User Identity**: The `users` table holds authentication credentials. Email uniqueness is case-insensitively indexed (`UNIQUE (lower(email))`).
- **Scoped Tenant Membership**: Roles (`agency_admin`, `agency_member`, `client_user`) are stored exclusively in `agency_memberships`, never on the `users` table.
- **Context Resolution**:
  - The JWT token contains `sub: user_id`.
  - The client passes `X-Agency-ID: <agency_uuid>` on each request.
  - The `get_membership` dependency fetches the specific role and client linkage for that user in that agency.
  - An individual (e.g. Alex) can log in once and toggle between acting as an `agency_admin` in Agency A and a restricted `client_user` in Agency B with no permission cross-contamination.

---

## 4. Edge Case: Member Removal Mid-Task & Backlog Preservation

**Policy Decision**: When an agency member is removed mid-sprint while assigned to tasks:
1. **Incomplete Tasks (`todo`, `in_progress`, `review`)**: Unassigned (`assignee_id = NULL`) by default so they immediately return to the project backlog for reallocation and are not blocked. An administrator can explicitly preserve assignments with `unassign_active=false` when needed.
2. **Completed Tasks (`done`)**: Retain `assignee_id = user_id` to preserve historical audit attribution, timesheets, and performance history.
3. **User Record Preserved**: The user's account in `users` is never deleted, as they may belong to other agencies or be invited back later.
4. **Immediate Access Revocation**: Project membership in `project_members` is deleted, instantly returning `404` on any subsequent attempt by that user to read or modify project data.

**Implementation**:
- The API supports `DELETE /projects/{id}/members/{user_id}?unassign_active=true`.
- The database schema sets `assignee_id UUID REFERENCES users(id) ON DELETE SET NULL` as a safety net against hard user deletion.

---

## 5. Additional System Highlights

- **Invite Idempotency**: Pending invites use `UNIQUE (agency_id, lower(email)) WHERE status = 'pending'`. Resending updates the token and expiration rather than creating duplicate records; accepting twice reuses the identity safely.
- **Real File Uploads**: Multipart uploads (`POST /tasks/{id}/files/upload`) store assets to local disk storage (`uploads/`) with static serving at `/uploads/{uuid_filename}`.
- **Event Bus & Automations (Redis)**: Redis pub/sub dispatches events (`file_needs_changes`, `task_done`) and evaluates configurable agency automation rules (e.g., auto-reopening tasks when changes are requested).
- **Test Coverage**: 118 backend pytest integration tests (including explicit edge-case verifications) and 13 Vitest frontend unit tests. Backend tests initialize and seed an isolated `agencydesk_test` database.
