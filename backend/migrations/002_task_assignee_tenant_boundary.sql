-- Prevent direct SQL and application bugs from assigning a task to a user who
-- has no membership in that task's agency. Existing assignments are validated
-- while this migration is applied.
ALTER TABLE agency_memberships
    ADD CONSTRAINT unique_agency_user UNIQUE (agency_id, user_id);

ALTER TABLE tasks
    DROP CONSTRAINT IF EXISTS tasks_assignee_id_fkey;

ALTER TABLE tasks
    ADD CONSTRAINT task_assignee_same_agency
    FOREIGN KEY (agency_id, assignee_id)
    REFERENCES agency_memberships(agency_id, user_id)
    ON DELETE SET NULL (assignee_id);
