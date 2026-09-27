export type UserRole = 'agency_admin' | 'agency_member' | 'client_user';

export type TaskStatus = 'todo' | 'in_progress' | 'review' | 'done';
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent';
export type FileApprovalStatus = 'pending' | 'approved' | 'needs_changes';

export interface User {
  id: string;
  email: string;
  full_name: string;
  created_at?: string;
}

export interface Membership {
  agency_id: string;
  agency_name: string;
  role: UserRole;
  client_id?: string | null;
}

export interface Project {
  id: string;
  agency_id: string;
  client_id: string;
  client_name?: string;
  name: string;
  description?: string;
  task_count?: number;
  completed_task_count?: number;
  total_hours_logged?: number;
  created_at: string;
}

export interface Task {
  id: string;
  agency_id: string;
  project_id: string;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  assignee_id?: string | null;
  assignee_name?: string | null;
  due_date?: string | null;
  is_internal: boolean;
  created_at: string;
}

export interface TaskComment {
  id: string;
  agency_id: string;
  task_id: string;
  author_id: string;
  author_name?: string;
  content: string;
  is_internal: boolean;
  created_at: string;
}

export interface TaskFile {
  id: string;
  agency_id: string;
  task_id: string;
  uploader_id: string;
  uploader_name?: string;
  file_name: string;
  file_url: string;
  approval_status: FileApprovalStatus;
  is_internal: boolean;
  created_at: string;
}

export interface TimeEntry {
  id: string;
  agency_id: string;
  task_id: string;
  user_id: string;
  user_name?: string;
  duration_minutes: number;
  note?: string;
  entry_date: string;
  created_at: string;
}

export interface AgencyMember {
  id: string;
  full_name: string;
  email: string;
  role: string;
}

export interface AgencyClient {
  id: string;
  name: string;
}

export interface AppNotification {
  id: string;
  agency_id: string;
  user_id: string;
  title: string;
  message: string;
  type: string;
  entity_type?: string | null;
  entity_id?: string | null;
  is_read: boolean;
  created_at: string;
}

export interface AutomationRule {
  id: string;
  agency_id: string;
  name: string;
  trigger_event: string;
  action_type: string;
  action_config: { target_status?: TaskStatus } & Record<string, unknown>;
  is_enabled: boolean;
  created_at: string;
}
