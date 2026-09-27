import type {
  User,
  Membership,
  Project,
  Task,
  TaskComment,
  TaskFile,
  TimeEntry,
  AgencyMember,
  AgencyClient,
  TaskStatus,
  FileApprovalStatus,
  TaskPriority,
  AppNotification,
  AutomationRule,
} from './types';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class ApiService {
  private token: string | null = null;
  private activeAgencyId: string | null = null;

  constructor() {
    this.token = localStorage.getItem('agencydesk_token');
    this.activeAgencyId = localStorage.getItem('agencydesk_agency_id');
  }

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('agencydesk_token', token);
    } else {
      localStorage.removeItem('agencydesk_token');
    }
  }

  getToken(): string | null {
    return this.token;
  }

  setActiveAgencyId(agencyId: string | null) {
    this.activeAgencyId = agencyId;
    if (agencyId) {
      localStorage.setItem('agencydesk_agency_id', agencyId);
    } else {
      localStorage.removeItem('agencydesk_agency_id');
    }
  }

  getActiveAgencyId(): string | null {
    return this.activeAgencyId;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    if (this.activeAgencyId) {
      headers['X-Agency-ID'] = this.activeAgencyId;
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
      try {
        const errorJson = await response.json();
        if (errorJson.detail) {
          errorMessage = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail);
        }
      } catch {
        // ignore fallback
      }
      throw new Error(errorMessage);
    }

    return response.json() as Promise<T>;
  }

  // Auth Endpoints
  async login(email: string, password: string): Promise<{ token: string; user_id: string }> {
    const data = await this.request<{ token: string; user_id: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(data.token);
    return data;
  }

  async register(data: { email: string; password: string; full_name: string; agency_name: string }): Promise<{ token: string; user_id: string; active_agency_id: string }> {
    const res = await this.request<{ token: string; user_id: string; active_agency_id: string }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
    this.setToken(res.token);
    this.setActiveAgencyId(res.active_agency_id);
    return res;
  }

  async getCurrentUser(): Promise<User> {
    return this.request<User>('/auth/me');
  }

  async getMemberships(): Promise<Membership[]> {
    const res = await this.request<{ memberships: Membership[] }>('/auth/memberships');
    return res.memberships;
  }

  // Projects
  async getProjects(isClientUser = false): Promise<Project[]> {
    const endpoint = isClientUser ? '/portal/projects' : '/projects';
    const res = await this.request<{ projects: Project[] }>(endpoint);
    return res.projects;
  }

  async getProjectDetails(
    projectId: string,
    isClientUser = false
  ): Promise<{ project: Project; tasks: Task[]; total_hours_logged?: number }> {
    const endpoint = isClientUser ? `/portal/projects/${projectId}` : `/projects/${projectId}`;
    return this.request<{ project: Project; tasks: Task[]; total_hours_logged?: number }>(endpoint);
  }

  // Tasks
  async createTask(data: {
    project_id: string;
    title: string;
    status?: TaskStatus;
    priority?: TaskPriority;
    assignee_id?: string | null;
    due_date?: string | null;
    is_internal?: boolean;
  }): Promise<Task> {
    return this.request<Task>('/tasks', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateTaskStatus(taskId: string, status: TaskStatus): Promise<{ id: string; status: TaskStatus }> {
    return this.request<{ id: string; status: TaskStatus }>(`/tasks/${taskId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
  }

  async updateTaskVisibility(taskId: string, isInternal: boolean): Promise<{ id: string; is_internal: boolean }> {
    return this.request<{ id: string; is_internal: boolean }>(`/tasks/${taskId}/visibility`, {
      method: 'PATCH',
      body: JSON.stringify({ is_internal: isInternal }),
    });
  }

  // Comments
  async getComments(taskId: string): Promise<TaskComment[]> {
    const res = await this.request<{ comments: TaskComment[] }>(`/tasks/${taskId}/comments`);
    return res.comments;
  }

  async addComment(taskId: string, content: string, isInternal = false): Promise<TaskComment> {
    return this.request<TaskComment>(`/tasks/${taskId}/comments`, {
      method: 'POST',
      body: JSON.stringify({ content, is_internal: isInternal }),
    });
  }

  // Deliverables & Files
  async getTaskFiles(taskId: string): Promise<TaskFile[]> {
    const res = await this.request<{ files: TaskFile[] }>(`/tasks/${taskId}/files`);
    return res.files;
  }

  async uploadTaskFile(taskId: string, fileName: string, fileUrl?: string, isInternal = false): Promise<TaskFile> {
    return this.request<TaskFile>(`/tasks/${taskId}/files`, {
      method: 'POST',
      body: JSON.stringify({
        file_name: fileName,
        file_url: fileUrl || `https://assets.agencydesk.internal/files/${encodeURIComponent(fileName)}`,
        is_internal: isInternal,
      }),
    });
  }

  async updateFileApproval(fileId: string, approvalStatus: 'approved' | 'needs_changes'): Promise<{ id: string; approval_status: FileApprovalStatus }> {
    return this.request<{ id: string; approval_status: FileApprovalStatus }>(`/files/${fileId}/approval`, {
      method: 'PATCH',
      body: JSON.stringify({ approval_status: approvalStatus }),
    });
  }

  // Time Entries
  async getTaskTimeEntries(taskId: string): Promise<TimeEntry[]> {
    const res = await this.request<{ time_entries: TimeEntry[] }>(`/tasks/${taskId}/time`);
    return res.time_entries;
  }

  async logTime(taskId: string, durationMinutes: number, note?: string, entryDate?: string): Promise<TimeEntry> {
    return this.request<TimeEntry>(`/tasks/${taskId}/time`, {
      method: 'POST',
      body: JSON.stringify({
        duration_minutes: durationMinutes,
        note: note || '',
        entry_date: entryDate || new Date().toISOString().slice(0, 10),
      }),
    });
  }

  // Agency staff & clients
  async getAgencyMembers(): Promise<AgencyMember[]> {
    const res = await this.request<{ members: AgencyMember[] }>('/agency/members');
    return res.members;
  }

  async getAgencyClients(): Promise<AgencyClient[]> {
    const res = await this.request<{ clients: AgencyClient[] }>('/agency/clients');
    return res.clients;
  }

  // Notifications
  async getNotifications(unreadOnly = false): Promise<{ notifications: AppNotification[]; unread_count: number }> {
    return this.request<{ notifications: AppNotification[]; unread_count: number }>(
      `/notifications?unread_only=${unreadOnly}`
    );
  }

  async getUnreadNotificationCount(): Promise<{ unread_count: number }> {
    return this.request<{ unread_count: number }>('/notifications/unread-count');
  }

  async markNotificationAsRead(id: string): Promise<AppNotification> {
    return this.request<AppNotification>(`/notifications/${id}/read`, {
      method: 'PATCH',
    });
  }

  async markAllNotificationsRead(): Promise<{ success: boolean; marked_count: number }> {
    return this.request<{ success: boolean; marked_count: number }>('/notifications/read-all', {
      method: 'POST',
    });
  }

  // Automations
  async getAutomations(): Promise<AutomationRule[]> {
    const res = await this.request<{ automations: AutomationRule[] }>('/automations');
    return res.automations;
  }

  async updateAutomation(id: string, data: { name?: string; is_enabled?: boolean }): Promise<AutomationRule> {
    return this.request<AutomationRule>(`/automations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }
}

export const api = new ApiService();
