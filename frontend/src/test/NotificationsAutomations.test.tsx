import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { Header } from '../components/Header';
import * as AuthContextModule from '../context/AuthContext';
import { api } from '../api';

describe('Notifications and Header Actions Frontend Components', () => {
  const baseAuthMock = {
    user: { id: 'u1', email: 'alex@example.com', full_name: 'Alex Rivera' },
    token: 'fake-jwt',
    memberships: [
      { agency_id: 'a1', agency_name: 'Acme Digital Agency', role: 'agency_admin' as const },
    ],
    activeAgency: { agency_id: 'a1', agency_name: 'Acme Digital Agency', role: 'agency_admin' as const },
    activeRole: 'agency_admin' as const,
    isClientUser: false,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    switchAgency: vi.fn(),
    quickLogin: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders notification bell with unread badge and opens popover', async () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue(baseAuthMock);
    vi.spyOn(api, 'getUnreadNotificationCount').mockResolvedValue({ unread_count: 2 });
    vi.spyOn(api, 'getNotifications').mockResolvedValue({
      notifications: [
        {
          id: 'n1',
          agency_id: 'a1',
          user_id: 'u1',
          title: 'Task Assigned',
          message: 'Assigned to wireframes',
          type: 'task_assigned',
          is_read: false,
          created_at: new Date().toISOString(),
        },
      ],
      unread_count: 1,
    });

    render(<Header />);

    // Unread count badge should appear
    await waitFor(() => {
      expect(screen.getByText('2')).toBeInTheDocument();
    });

    // Click bell icon
    const bellBtn = screen.getByLabelText(/View notifications/i);
    fireEvent.click(bellBtn);

    // Dropdown is open
    expect(screen.getByTestId('notification-dropdown')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Task Assigned')).toBeInTheDocument();
      expect(screen.getByText('Assigned to wireframes')).toBeInTheDocument();
    });
  });

  it('does not render Automations button for any user in Header', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      ...baseAuthMock,
      activeRole: 'client_user',
      isClientUser: true,
    });

    render(<Header />);

    // Automations button must NOT be rendered for client
    expect(screen.queryByText(/⚡ Automations/)).not.toBeInTheDocument();
  });

  it('renders New Project and Team buttons for agency admin in Header', async () => {
    const onOpenNewProject = vi.fn();
    const onOpenTeamModal = vi.fn();

    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue(baseAuthMock);

    render(<Header onOpenNewProject={onOpenNewProject} onOpenTeamModal={onOpenTeamModal} />);

    // Automations button must NOT be rendered
    expect(screen.queryByText(/⚡ Automations/)).not.toBeInTheDocument();

    const newProjectBtn = screen.getByText('+ New Project');
    expect(newProjectBtn).toBeInTheDocument();
    fireEvent.click(newProjectBtn);
    expect(onOpenNewProject).toHaveBeenCalledTimes(1);

    const teamBtn = screen.getByText('👥 Team & Clients');
    expect(teamBtn).toBeInTheDocument();
    fireEvent.click(teamBtn);
    expect(onOpenTeamModal).toHaveBeenCalledTimes(1);
  });
});
