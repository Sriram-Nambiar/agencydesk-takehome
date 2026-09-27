import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { User, Membership, UserRole } from '../types';
import { api } from '../api';

interface AuthContextType {
  user: User | null;
  memberships: Membership[];
  activeAgency: Membership | null;
  activeRole: UserRole | null;
  isClientUser: boolean;
  isLoading: boolean;
  error: string | null;
  login: (email: string, pass: string) => Promise<void>;
  register: (data: { email: string; password: string; full_name: string; agency_name: string }) => Promise<void>;
  logout: () => void;
  switchAgency: (agencyId: string) => void;
  quickLogin: (persona: 'admin' | 'member' | 'client') => Promise<void>;
  refreshAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [activeAgency, setActiveAgency] = useState<Membership | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const initSession = useCallback(async () => {
    const token = api.getToken();
    if (!token) {
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      setError(null);
      const [userData, membershipList] = await Promise.all([
        api.getCurrentUser(),
        api.getMemberships(),
      ]);

      setUser(userData);
      setMemberships(membershipList);

      const savedAgencyId = api.getActiveAgencyId();
      const matched = membershipList.find((m) => m.agency_id === savedAgencyId);
      if (matched) {
        setActiveAgency(matched);
        api.setActiveAgencyId(matched.agency_id);
      } else if (membershipList.length > 0) {
        setActiveAgency(membershipList[0]);
        api.setActiveAgencyId(membershipList[0].agency_id);
      } else {
        setActiveAgency(null);
      }
    } catch (err: unknown) {
      console.warn('Session init failed:', err);
      api.setToken(null);
      setUser(null);
      setMemberships([]);
      setActiveAgency(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial async session restoration is the external-system sync for this provider.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    initSession();
  }, [initSession]);

  const login = async (email: string, pass: string) => {
    setIsLoading(true);
    setError(null);
    try {
      await api.login(email, pass);
      await initSession();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Login failed';
      setError(msg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (data: { email: string; password: string; full_name: string; agency_name: string }) => {
    setIsLoading(true);
    setError(null);
    try {
      await api.register(data);
      await initSession();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Registration failed';
      setError(msg);
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = () => {
    api.setToken(null);
    api.setActiveAgencyId(null);
    setUser(null);
    setMemberships([]);
    setActiveAgency(null);
    setError(null);
  };

  const switchAgency = (agencyId: string) => {
    const target = memberships.find((m) => m.agency_id === agencyId);
    if (target) {
      setActiveAgency(target);
      api.setActiveAgencyId(target.agency_id);
    }
  };

  const quickLogin = async (persona: 'admin' | 'member' | 'client') => {
    const emails = {
      admin: 'alex@example.com',
      member: 'sarah@acme.com',
      client: 'john@starlight.com',
    };
    await login(emails[persona], 'password123');
  };

  const activeRole: UserRole | null = activeAgency ? activeAgency.role : null;
  const isClientUser = activeRole === 'client_user';

  return (
    <AuthContext.Provider
      value={{
        user,
        memberships,
        activeAgency,
        activeRole,
        isClientUser,
        isLoading,
        error,
        login,
        register,
        logout,
        switchAgency,
        quickLogin,
        refreshAuth: initSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

// Shared hook export is intentionally colocated with its provider and context.
// eslint-disable-next-line react-refresh/only-export-components
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
