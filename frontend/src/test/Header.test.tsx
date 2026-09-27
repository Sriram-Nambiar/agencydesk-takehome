import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Header } from '../components/Header';
import * as AuthContextModule from '../context/AuthContext';

describe('Header Component', () => {
  const mockSwitchAgency = vi.fn();
  const mockLogout = vi.fn();
  const mockQuickLogin = vi.fn();

  const baseAuthMock = {
    token: 'fake-token',
    user: { id: 'u1', email: 'alex@example.com', full_name: 'Alex Rivera' },
    memberships: [
      { agency_id: 'a1', agency_name: 'Acme Digital Agency', role: 'agency_admin', client_id: null },
      { agency_id: 'a2', agency_name: 'Beta Media Group', role: 'client_user', client_id: 'c1' },
    ],
    activeAgency: { agency_id: 'a1', agency_name: 'Acme Digital Agency', role: 'agency_admin', client_id: null },
    activeRole: 'agency_admin' as const,
    activeClientId: null,
    isClientUser: false,
    switchAgency: mockSwitchAgency,
    login: vi.fn(),
    logout: mockLogout,
    quickLogin: mockQuickLogin,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders application brand and user name', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue(baseAuthMock as any);
    render(<Header />);

    expect(screen.getByText('AgencyDesk')).toBeInTheDocument();
    expect(screen.getByText('Alex Rivera')).toBeInTheDocument();
    expect(screen.getByText('Agency Admin')).toBeInTheDocument();
  });

  it('renders Staff badge when activeRole is agency_member', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      ...baseAuthMock,
      user: { id: 'u2', email: 'sarah@acme.com', full_name: 'Sarah Chen' },
      activeRole: 'agency_member',
    } as any);
    render(<Header />);

    expect(screen.getByText('Sarah Chen')).toBeInTheDocument();
    expect(screen.getByText('Agency Staff')).toBeInTheDocument();
  });

  it('renders Client Portal badge when activeRole is client_user', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      ...baseAuthMock,
      user: { id: 'u3', email: 'john@starlight.com', full_name: 'John Starlight' },
      activeRole: 'client_user',
      isClientUser: true,
    } as any);
    render(<Header />);

    expect(screen.getByText('John Starlight')).toBeInTheDocument();
    expect(screen.getByText('Client Portal')).toBeInTheDocument();
  });

  it('allows tenant switching between memberships', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue(baseAuthMock as any);
    render(<Header />);

    const select = screen.getByLabelText(/Agency:/i);
    fireEvent.change(select, { target: { value: 'a2' } });

    expect(mockSwitchAgency).toHaveBeenCalledWith('a2');
  });

  it('triggers quick login for demo users', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue(baseAuthMock as any);
    render(<Header />);

    fireEvent.click(screen.getByTitle('Log in as Sarah (Staff)'));
    expect(mockQuickLogin).toHaveBeenCalledWith('member');

    fireEvent.click(screen.getByTitle('Log in as John (Client)'));
    expect(mockQuickLogin).toHaveBeenCalledWith('client');
  });

  it('calls logout on Sign Out button click', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue(baseAuthMock as any);
    render(<Header />);

    fireEvent.click(screen.getByRole('button', { name: /Sign Out/i }));
    expect(mockLogout).toHaveBeenCalledTimes(1);
  });
});
