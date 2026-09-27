-- Apply to a database created from the earlier AgencyDesk schema.
-- Check for case-insensitive duplicate user emails before applying the unique index.
CREATE UNIQUE INDEX IF NOT EXISTS users_email_case_insensitive ON users (lower(email));

ALTER TABLE clients ADD CONSTRAINT clients_agency_id_id_key UNIQUE (agency_id, id);
ALTER TABLE projects ADD CONSTRAINT projects_agency_id_id_key UNIQUE (agency_id, id);
ALTER TABLE projects ADD CONSTRAINT project_client_same_agency
    FOREIGN KEY (agency_id, client_id) REFERENCES clients(agency_id, id);
ALTER TABLE tasks ADD CONSTRAINT tasks_agency_id_id_key UNIQUE (agency_id, id);
ALTER TABLE agency_memberships ADD CONSTRAINT membership_client_same_agency
    FOREIGN KEY (agency_id, client_id) REFERENCES clients(agency_id, id);
ALTER TABLE agency_memberships ADD CONSTRAINT membership_client_role
    CHECK ((role = 'client_user' AND client_id IS NOT NULL) OR (role <> 'client_user' AND client_id IS NULL));
ALTER TABLE tasks ADD CONSTRAINT task_project_same_agency
    FOREIGN KEY (agency_id, project_id) REFERENCES projects(agency_id, id);
ALTER TABLE tasks ADD CONSTRAINT task_status_valid CHECK (status IN ('todo', 'in_progress', 'review', 'done'));
ALTER TABLE tasks ADD CONSTRAINT task_priority_valid CHECK (priority IN ('low', 'medium', 'high', 'urgent'));
ALTER TABLE task_comments ADD CONSTRAINT comment_task_same_agency
    FOREIGN KEY (agency_id, task_id) REFERENCES tasks(agency_id, id);
ALTER TABLE task_files ADD CONSTRAINT file_task_same_agency
    FOREIGN KEY (agency_id, task_id) REFERENCES tasks(agency_id, id);
ALTER TABLE time_entries ADD CONSTRAINT time_task_same_agency
    FOREIGN KEY (agency_id, task_id) REFERENCES tasks(agency_id, id);
ALTER TABLE agency_invites DROP CONSTRAINT IF EXISTS unique_agency_invite_email;
ALTER TABLE agency_invites ADD CONSTRAINT invite_client_same_agency
    FOREIGN KEY (agency_id, client_id) REFERENCES clients(agency_id, id);
ALTER TABLE agency_invites ADD CONSTRAINT invite_client_role
    CHECK ((role = 'client_user' AND client_id IS NOT NULL) OR (role <> 'client_user' AND client_id IS NULL));
CREATE UNIQUE INDEX unique_pending_agency_invite_email
    ON agency_invites (agency_id, lower(email)) WHERE status = 'pending';

-- PROJECT MEMBERS ISOLATION CONSTRAINTS
ALTER TABLE project_members ADD COLUMN IF NOT EXISTS agency_id UUID REFERENCES agencies(id) ON DELETE CASCADE;
UPDATE project_members pm SET agency_id = p.agency_id FROM projects p WHERE pm.project_id = p.id AND pm.agency_id IS NULL;
CREATE OR REPLACE FUNCTION set_project_member_agency_id()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.agency_id IS NULL THEN
        SELECT agency_id INTO NEW.agency_id FROM projects WHERE id = NEW.project_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_set_pm_agency_id ON project_members;
CREATE TRIGGER trg_set_pm_agency_id
BEFORE INSERT ON project_members
FOR EACH ROW
EXECUTE FUNCTION set_project_member_agency_id();
ALTER TABLE project_members DROP CONSTRAINT IF EXISTS pm_project_same_agency;
ALTER TABLE project_members ADD CONSTRAINT pm_project_same_agency
    FOREIGN KEY (agency_id, project_id) REFERENCES projects(agency_id, id) ON DELETE CASCADE;
ALTER TABLE project_members DROP CONSTRAINT IF EXISTS pm_user_same_agency;
ALTER TABLE project_members ADD CONSTRAINT pm_user_same_agency
    FOREIGN KEY (user_id, agency_id) REFERENCES agency_memberships(user_id, agency_id) ON DELETE CASCADE;
