import { useState } from 'react';
import type { NavigateFn } from '../App';

function ShieldIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

export default function LoginScreen({ navigate }: { navigate: NavigateFn }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSignIn = () => {
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      navigate('dashboard');
    }, 800);
  };

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: '#07091d',
      backgroundImage: 'radial-gradient(ellipse at 20% 50%, #0f1e4a18 0%, transparent 60%), radial-gradient(ellipse at 80% 20%, #1a3880 08 0%, transparent 50%)',
    }}>
      {/* Grid overlay */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none',
        backgroundImage: 'linear-gradient(#18234a18 1px, transparent 1px), linear-gradient(90deg, #18234a18 1px, transparent 1px)',
        backgroundSize: '48px 48px',
      }} />

      <div style={{ position: 'relative', width: '100%', maxWidth: 400, padding: '0 20px' }}>
        {/* Card */}
        <div style={{
          background: '#0e1233',
          border: '1px solid #18234a',
          borderRadius: 16,
          padding: '40px 36px',
          boxShadow: '0 24px 80px #020408a0',
        }}>
          {/* Header */}
          <div style={{ textAlign: 'center', marginBottom: 36 }}>
            <div style={{
              width: 60, height: 60, borderRadius: 14,
              background: 'linear-gradient(135deg, #1a3a80 0%, #2860d0 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 16px',
              color: '#a0c8ff',
              boxShadow: '0 0 24px #2860d040',
            }}>
              <ShieldIcon />
            </div>
            <h1 style={{ margin: '0 0 4px', fontSize: 24, fontWeight: 700, color: '#d5dffa', letterSpacing: '-0.01em' }}>VoiceShield</h1>
            <p style={{ margin: 0, fontSize: 13, color: '#6280b8' }}>AI-Powered Security Gateway</p>
          </div>

          {/* Form */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>
                Email Address
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="admin@organization.gov"
                style={{
                  width: '100%', padding: '10px 14px',
                  background: '#080c24', border: '1px solid #18234a',
                  borderRadius: 8, color: '#d5dffa', fontSize: 14,
                  outline: 'none', transition: 'border-color 0.15s',
                }}
                onFocus={e => (e.target.style.borderColor = '#2a4a90')}
                onBlur={e => (e.target.style.borderColor = '#18234a')}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••••••"
                style={{
                  width: '100%', padding: '10px 14px',
                  background: '#080c24', border: '1px solid #18234a',
                  borderRadius: 8, color: '#d5dffa', fontSize: 14,
                  outline: 'none', transition: 'border-color 0.15s',
                }}
                onFocus={e => (e.target.style.borderColor = '#2a4a90')}
                onBlur={e => (e.target.style.borderColor = '#18234a')}
                onKeyDown={e => e.key === 'Enter' && handleSignIn()}
              />
            </div>
            <button
              onClick={handleSignIn}
              disabled={loading}
              style={{
                marginTop: 8, padding: '11px',
                background: loading ? '#1a3060' : '#1e4090',
                border: '1px solid #2a5acc',
                borderRadius: 8, color: '#a0c0f8',
                fontSize: 14, fontWeight: 600, cursor: loading ? 'wait' : 'pointer',
                transition: 'all 0.15s', letterSpacing: '0.02em',
              }}
              onMouseEnter={e => !loading && ((e.currentTarget as HTMLButtonElement).style.background = '#254aac')}
              onMouseLeave={e => !loading && ((e.currentTarget as HTMLButtonElement).style.background = '#1e4090')}
            >
              {loading ? 'Authenticating…' : 'Sign In'}
            </button>
          </div>

          {/* Footer */}
          <div style={{ marginTop: 28, paddingTop: 20, borderTop: '1px solid #18234a', textAlign: 'center' }}>
            <div style={{ fontSize: 11, color: '#3a4e78', letterSpacing: '0.06em' }}>SECURE ENTERPRISE ACCESS</div>
            <div style={{ fontSize: 11, color: '#2a3a58', marginTop: 4 }}>Authorized Access Only — All activity is monitored and logged</div>
          </div>
        </div>

        {/* Demo hint */}
        <p style={{ textAlign: 'center', fontSize: 11, color: '#2a3a58', marginTop: 16 }}>
          Demo prototype — use any credentials to proceed
        </p>
      </div>
    </div>
  );
}
