import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ProjectOverview } from '../components/ProjectOverview';
import { TaskBoard } from '../components/TaskBoard';
import * as AuthContextModule from '../context/AuthContext';
import type { Project, Task } from '../types';

describe('Frontend Leak Shield & Role Boundary Controls', () => {
  const sampleProject: Project = {
    id: 'proj-1',
    agency_id: 'agency-1',
    client_id: 'client-1',
    name: 'Website Redesign',
    client_name: 'Starlight Tech',
    created_at: '2026-09-01T00:00:00Z',
    task_count: 5,
    completed_task_count: 2,
    total_hours_logged: 12.5,
  };

  const sampleTasks: Task[] = [
    {
      id: 'task-1',
      agency_id: 'agency-1',
      project_id: 'proj-1',
      title: 'Draft Client Wireframes',
      status: 'todo',
      priority: 'high',
      assignee_id: 'u1',
      assignee_name: 'Sarah Chen',
      due_date: '2026-10-15',
      is_internal: false,
      created_at: '2026-09-02T00:00:00Z',
    },
    {
      id: 'task-2',
      agency_id: 'agency-1',
      project_id: 'proj-1',
      title: 'Internal DB Migration Note',
      status: 'in_progress',
      priority: 'urgent',
      assignee_id: 'u1',
      assignee_name: 'Sarah Chen',
      due_date: '2026-10-10',
      is_internal: true,
      created_at: '2026-09-03T00:00:00Z',
    },
  ];

  it('ProjectOverview displays staff controls (Add Task, Logged Time) when logged in as agency staff', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isClientUser: false,
      activeRole: 'agency_admin',
    } as any);

    render(
      <ProjectOverview
        projects={[sampleProject]}
        selectedProject={sampleProject}
        onSelectProject={vi.fn()}
        viewMode="board"
        onChangeViewMode={vi.fn()}
        searchQuery=""
        onSearchChange={vi.fn()}
        priorityFilter="all"
        onPriorityFilterChange={vi.fn()}
        showInternalOnly={false}
        onToggleInternalOnly={vi.fn()}
        onOpenNewTaskModal={vi.fn()}
        totalHoursLogged={12.5}
        tasksCount={5}
        completedTasksCount={2}
      />
    );

    // Staff sees "+ Add New Task"
    expect(screen.getByRole('button', { name: /\+ Add New Task/i })).toBeInTheDocument();
    // Staff sees "Logged Time"
    expect(screen.getByText(/Logged Time/i)).toBeInTheDocument();
    expect(screen.getByText(/12.5 hrs/i)).toBeInTheDocument();
    // Staff sees "Staff only tasks" checkbox
    expect(screen.getByText(/Staff only tasks/i)).toBeInTheDocument();
    // Staff DOES NOT see client shield notice banner
    expect(screen.queryByText(/Client Portal:/i)).not.toBeInTheDocument();
  });

  it('ProjectOverview strictly shields and hides staff controls when logged in as client user', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isClientUser: true,
      activeRole: 'client_user',
    } as any);

    render(
      <ProjectOverview
        projects={[sampleProject]}
        selectedProject={sampleProject}
        onSelectProject={vi.fn()}
        viewMode="board"
        onChangeViewMode={vi.fn()}
        searchQuery=""
        onSearchChange={vi.fn()}
        priorityFilter="all"
        onPriorityFilterChange={vi.fn()}
        showInternalOnly={false}
        onToggleInternalOnly={vi.fn()}
        onOpenNewTaskModal={vi.fn()}
        totalHoursLogged={12.5}
        tasksCount={5}
        completedTasksCount={2}
      />
    );

    // Client CANNOT see "+ Add New Task"
    expect(screen.queryByRole('button', { name: /\+ Add New Task/i })).not.toBeInTheDocument();
    // Client CANNOT see "Logged Time"
    expect(screen.queryByText(/Logged Time/i)).not.toBeInTheDocument();
    // Client CANNOT see "Staff only tasks" filter
    expect(screen.queryByText(/Staff only tasks/i)).not.toBeInTheDocument();
    // Client DOES see client shield notice
    expect(screen.getByText(/Client Portal:/i)).toBeInTheDocument();
    expect(screen.getByText(/Internal tasks, draft notes, and staff time entries are protected/i)).toBeInTheDocument();
  });

  it('TaskBoard renders move status button for staff and triggers status update', () => {
    const mockUpdateStatus = vi.fn();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isClientUser: false,
    } as any);

    render(
      <TaskBoard
        tasks={sampleTasks}
        onSelectTask={vi.fn()}
        onUpdateStatus={mockUpdateStatus}
      />
    );

    // Staff sees "Move → in progress" button on todo task
    const moveBtn = screen.getByRole('button', { name: /Move → in progress/i });
    expect(moveBtn).toBeInTheDocument();

    fireEvent.click(moveBtn);
    expect(mockUpdateStatus).toHaveBeenCalledWith('task-1', 'in_progress');

    // Staff sees "Internal" badge on internal task
    expect(screen.getByText('Internal')).toBeInTheDocument();
  });

  it('TaskBoard hides status transition controls for client users', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      isClientUser: true,
    } as any);

    render(
      <TaskBoard
        tasks={sampleTasks}
        onSelectTask={vi.fn()}
        onUpdateStatus={vi.fn()}
      />
    );

    // Client CANNOT see move status buttons
    expect(screen.queryByRole('button', { name: /Move →/i })).not.toBeInTheDocument();
  });
});
