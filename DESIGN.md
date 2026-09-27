# AgencyDesk design notes

Every request derives a user from a signed bearer token and requires an active agency membership for the supplied `X-Agency-ID`. Queries include that agency id, and composite foreign keys on projects, tasks, comments, files, time entries, and client memberships reject cross-agency references even if application code supplies mismatched IDs. Agency members are additionally limited to projects listed in `project_members`; removing that membership immediately removes access. A task assignee is set to `NULL` when its user is deleted, preserving the task.

Client access is scoped to the membership's client record. Shared project/task access checks run before detail, comments, file, and time routes. Client task queries exclude internal tasks; comment and file queries independently exclude internal records; internal tasks and their child records return not found to clients, including when IDs are guessed. Clients cannot change task status or log time. They can comment on visible tasks and approve or request changes on visible files. Staff time data is not returned through portal endpoints.

`users` represent global identities with a case-insensitive unique email. `agency_memberships` assigns a separate role and optional client to that identity for each agency, so the same person can be staff in one tenant and a client in another. Invites are unique while pending per agency/email; resending rotates the existing pending invite instead of creating duplicates. (Invite acceptance can reuse an existing identity.)

One edge case handled explicitly is a member losing project access while a task is assigned to them: an admin can remove their project membership through the API; project membership is checked on each request, so access ends immediately without deleting task history or the assignee relationship. Hard user deletion still nulls the assignee via `ON DELETE SET NULL`.
 
## Event-Driven Automations & Notifications (Redis Architecture)
 
AgencyDesk implements an event bus and workflow automation engine powered by Redis (`redis:7-alpine`):
 
1. **Redis Pub/Sub & Queues**: Business events (`task_created`, `task_status_changed`, `comment_created`, `file_status_changed`) publish payloads to Redis channels (`agencydesk:events:{agency_id}`, `agencydesk:notify:{user_id}`) and append to the FIFO persistent queue `agencydesk:events_queue`.
2. **Sub-millisecond Unread Badge Caching**: User unread notification counts are cached in Redis (`agencydesk:unread:{agency_id}:{user_id}`). When new notifications arrive or users mark items as read, Redis caches are automatically invalidated.
3. **Automated Workflows (`automations` table)**: Tenant-configurable rules react to events. For example, when a client marks a deliverable as `needs_changes`, the automation engine instantly updates the parent task status back to `in_progress` and dispatches an alert to the assigned agency member.
4. **Leak-Shield Compliance in Notifications**: The notification dispatcher enforces boundary policies identical to the REST API: client users are never alerted to internal tasks or internal agency comments, and `/automations` endpoints reject client users with HTTP 403 Forbidden.
