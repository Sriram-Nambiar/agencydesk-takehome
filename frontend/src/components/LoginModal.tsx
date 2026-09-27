import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export const LoginModal: React.FC = () => {
  const { login, register, quickLogin, error, isLoading } = useAuth();
  const [isRegistering, setIsRegistering] = useState(false);

  // Custom login state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  // Register state
  const [regFullName, setRegFullName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regAgencyName, setRegAgencyName] = useState('');

  const [formError, setFormError] = useState<string | null>(null);

  const handleCustomLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    try {
      await login(email, password);
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Login failed');
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    try {
      await register({
        full_name: regFullName,
        email: regEmail,
        password: regPassword,
        agency_name: regAgencyName,
      });
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : 'Registration failed');
    }
  };

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="login-title-box">
          <h1>AgencyDesk</h1>
          <p>Multi-tenant Agency & Client Portal</p>
        </div>

        {(error || formError) && (
          <div className="error-banner">{formError || error}</div>
        )}

        {/* Quick Demo Test Accounts Box */}
        <div className="demo-accounts-box">
          <h4>Quick Demo Logins (Click to sign in):</h4>
          <div className="demo-buttons-col">
            <button
              type="button"
              className="demo-account-btn"
              onClick={() => quickLogin('admin')}
              disabled={isLoading}
            >
              <span><strong>Alex Rivera</strong> (Agency Admin)</span>
              <span className="badge badge-admin">Dual Tenant</span>
            </button>

            <button
              type="button"
              className="demo-account-btn"
              onClick={() => quickLogin('member')}
              disabled={isLoading}
            >
              <span><strong>Sarah Chen</strong> (Agency Staff)</span>
              <span className="badge badge-member">Acme</span>
            </button>

            <button
              type="button"
              className="demo-account-btn"
              onClick={() => quickLogin('client')}
              disabled={isLoading}
            >
              <span><strong>John Starlight</strong> (Client User)</span>
              <span className="badge badge-client">Portal</span>
            </button>
          </div>
        </div>

        {/* Custom Login / Register Form */}
        {!isRegistering ? (
          <form onSubmit={handleCustomLogin}>
            <div className="form-group">
              <label className="form-label">Email Address</label>
              <input
                type="email"
                required
                className="form-input"
                placeholder="name@agency.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Password</label>
              <input
                type="password"
                required
                className="form-input"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', padding: '8px' }}
              disabled={isLoading}
            >
              {isLoading ? 'Signing In...' : 'Sign In'}
            </button>

            <div style={{ marginTop: 14, textAlign: 'center', fontSize: 13 }}>
              Need a new agency?{' '}
              <button
                type="button"
                style={{ color: '#0052cc', fontWeight: 600 }}
                onClick={() => {
                  setIsRegistering(true);
                  setFormError(null);
                }}
              >
                Register Agency
              </button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleRegister}>
            <div className="form-group">
              <label className="form-label">Agency Name</label>
              <input
                type="text"
                required
                className="form-input"
                placeholder="e.g. Apex Digital"
                value={regAgencyName}
                onChange={(e) => setRegAgencyName(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Full Name</label>
              <input
                type="text"
                required
                className="form-input"
                placeholder="e.g. Alex Rivera"
                value={regFullName}
                onChange={(e) => setRegFullName(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Email Address</label>
              <input
                type="email"
                required
                className="form-input"
                placeholder="alex@apex.com"
                value={regEmail}
                onChange={(e) => setRegEmail(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Password</label>
              <input
                type="password"
                required
                className="form-input"
                placeholder="••••••••"
                value={regPassword}
                onChange={(e) => setRegPassword(e.target.value)}
              />
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              style={{ width: '100%', padding: '8px' }}
              disabled={isLoading}
            >
              {isLoading ? 'Creating...' : 'Create Agency & Sign In'}
            </button>

            <div style={{ marginTop: 14, textAlign: 'center', fontSize: 13 }}>
              Already registered?{' '}
              <button
                type="button"
                style={{ color: '#0052cc', fontWeight: 600 }}
                onClick={() => {
                  setIsRegistering(false);
                  setFormError(null);
                }}
              >
                Sign In
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
