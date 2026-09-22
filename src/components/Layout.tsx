import { useState, useEffect, type ReactNode } from 'react';
import type { Screen, NavigateFn } from '../App';

interface LayoutProps {
  currentScreen: Screen;
  navigate: NavigateFn;
  children: ReactNode;
}

function ShieldIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

const NAV_ITEMS: { id: Screen; label: string; icon: ReactNode }[] = [
  {
    id: 'dashboard', label: 'Dashboard',
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /></svg>,
  },
  {
    id: 'live-calls', label: 'Live Calls',
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 013.07 9.81 19.79 19.79 0 01.22 1.18 2 2 0 012.22.2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L6.09 7.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z" /></svg>,
  },
  {
    id: 'alerts', label: 'Alerts',
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" /></svg>,
  },
  {
    id: 'audit-trail', label: 'Audit Trail',
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" /><polyline points="14 2 14 8 20 8" /><line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" /></svg>,
  },
  {
    id: 'trusted-users', label: 'Trusted Users',
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75" /></svg>,
  },
  {
    id: 'security-policies', label: 'Security Policies',
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0110 0v4" /></svg>,
  },
  {
    id: 'system-status', label: 'System Status',
    icon: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2" /><line x1="8" y1="21" x2="16" y2="21" /><line x1="12" y1="17" x2="12" y2="21" /></svg>,
  },
];

function parentScreen(screen: Screen): Screen {
  if (screen === 'session-detail') return 'live-calls';
  if (screen === 'alert-detail') return 'alerts';
  if (screen === 'register-user') return 'trusted-users';
  return screen;
}

function StatusDot({ label, color }: { label: string; color: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 6, height: 6, borderRadius: '50%', background: color, boxShadow: `0 0 5px ${color}80`, flexShrink: 0 }} />
      <span style={{ fontSize: 11, color: '#4060a0' }}>{label}</span>
    </div>
  );
}

export default function Layout({ currentScreen, navigate, children }: LayoutProps) {
  const [clock, setClock] = useState(() => new Date().toLocaleTimeString('en-US', { hour12: false }));
  const active = parentScreen(currentScreen);

  useEffect(() => {
    const id = setInterval(() => setClock(new Date().toLocaleTimeString('en-US', { hour12: false })), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', background: '#07091d' }}>
      {/* Sidebar */}
      <aside style={{
        width: 220, flexShrink: 0, height: '100%',
        display: 'flex', flexDirection: 'column',
        background: '#080b22', borderRight: '1px solid #18234a',
        overflow: 'hidden',
      }}>
        {/* Logo */}
        <div style={{ padding: '18px 18px 14px', borderBottom: '1px solid #18234a' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 34, height: 34, borderRadius: 8,
              background: 'linear-gradient(135deg, #1a3a80 0%, #2860d0 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#a0c8ff', flexShrink: 0,
              boxShadow: '0 0 12px #2860d040',
            }}>
              <ShieldIcon />
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: '#d5dffa', letterSpacing: '0.02em' }}>VoiceShield</div>
              <div style={{ fontSize: 9, color: '#3a5090', letterSpacing: '0.12em', textTransform: 'uppercase', fontWeight: 600 }}>AI Security Gateway</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '10px 10px', overflowY: 'auto' }}>
          {NAV_ITEMS.map(item => {
            const isActive = active === item.id;
            return (
              <button
                key={item.id}
                onClick={() => navigate(item.id)}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                  padding: '8px 10px', marginBottom: 2, borderRadius: 6,
                  border: 'none', cursor: 'pointer', textAlign: 'left',
                  fontSize: 13, fontWeight: isActive ? 600 : 400,
                  color: isActive ? '#90b8f8' : '#5070a0',
                  background: isActive ? '#0f2050' : 'transparent',
                  transition: 'all 0.15s',
                }}
                onMouseEnter={e => {
                  if (!isActive) {
                    (e.currentTarget as HTMLButtonElement).style.background = '#0c1840';
                    (e.currentTarget as HTMLButtonElement).style.color = '#7898c8';
                  }
                }}
                onMouseLeave={e => {
                  if (!isActive) {
                    (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                    (e.currentTarget as HTMLButtonElement).style.color = '#5070a0';
                  }
                }}
              >
                <span style={{ opacity: isActive ? 1 : 0.7, flexShrink: 0 }}>{item.icon}</span>
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Gateway status */}
        <div style={{ padding: '12px 16px 16px', borderTop: '1px solid #18234a' }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: '#2a4070', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 10 }}>
            SECURE GATEWAY
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            <StatusDot label="Gateway Online" color="#20d870" />
            <StatusDot label="MCP Connected" color="#4080f8" />
            <StatusDot label="Fabric Connected" color="#4080f8" />
          </div>
        </div>
      </aside>

      {/* Right side */}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Top nav */}
        <header style={{
          height: 50, flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 24px',
          background: '#080b22', borderBottom: '1px solid #18234a',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 7, height: 7, borderRadius: '50%', background: '#20d870', boxShadow: '0 0 5px #20d87080' }} />
              <span style={{ fontSize: 11, fontWeight: 600, color: '#3a6038', letterSpacing: '0.08em' }}>SYSTEM OPERATIONAL</span>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
            <span style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 12, color: '#4060a0', letterSpacing: '0.04em',
            }}>
              {clock} UTC
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ fontSize: 12, color: '#5070a0' }}>Admin User</div>
              <div style={{
                width: 28, height: 28, borderRadius: '50%',
                background: '#1a3060', border: '1px solid #2a4880',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 700, color: '#5888d8',
              }}>A</div>
            </div>
          </div>
        </header>

        {/* Main content */}
        <main style={{ flex: 1, overflow: 'auto', padding: '24px 28px' }}>
          {children}
        </main>
      </div>
    </div>
  );
}
