import { useEffect, useState } from 'react';
import type { NavigateFn } from '../App';
import { PageHeader, Card, Btn, ServiceBadge } from '../components/ui';
import { listUsers, type UserProfile } from '../lib/api';

const FALLBACK_USERS: UserProfile[] = [
  { id: 'USR-0041', name: 'Alex Chen', role: 'Finance Manager', dept: 'Treasury', profile: 'VP-041', status: 'Active', quality: 98, enrolled: '2026-03-12', emp_id: 'EMP-0041' },
  { id: 'USR-0038', name: 'Morgan Rivera', role: 'Branch Director', dept: 'Operations', profile: 'VP-038', status: 'Active', quality: 94, enrolled: '2026-03-08', emp_id: 'EMP-0038' },
  { id: 'USR-0031', name: 'Sam Patel', role: 'Senior Analyst', dept: 'Risk Management', profile: 'VP-031', status: 'Active', quality: 97, enrolled: '2026-02-20', emp_id: 'EMP-0031' },
  { id: 'USR-0027', name: 'Jordan Kim', role: 'Compliance Officer', dept: 'Legal', profile: 'VP-027', status: 'Active', quality: 99, enrolled: '2026-02-11', emp_id: 'EMP-0027' },
  { id: 'USR-0019', name: 'Taylor Wong', role: 'IT Security Lead', dept: 'IT Security', profile: 'VP-019', status: 'Active', quality: 96, enrolled: '2026-01-28', emp_id: 'EMP-0019' },
  { id: 'USR-0015', name: 'Casey Mbeki', role: 'Account Manager', dept: 'Client Services', profile: 'VP-015', status: 'Suspended', quality: 78, enrolled: '2026-01-14', emp_id: 'EMP-0015' },
  { id: 'USR-0009', name: 'Drew Okonkwo', role: 'Operations Analyst', dept: 'Operations', profile: 'VP-009', status: 'Active', quality: 91, enrolled: '2025-12-30', emp_id: 'EMP-0009' },
];

function DemoBadge({ text = 'DEMO — NON-FUNCTIONAL MOCKUP' }: { text?: string }) {
  return (
    <span style={{
      fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
      color: '#f5a020', background: '#2a1e06', border: '1px solid #f5a02050',
      padding: '2px 7px', borderRadius: 4, whiteSpace: 'nowrap',
    }}>
      {text}
    </span>
  );
}

function QualityBar({ value }: { value: number }) {
  const color = value >= 90 ? '#20d870' : value >= 75 ? '#f5a020' : '#f03838';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ width: 60, height: 4, background: '#18234a', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${value}%`, background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color }}>{value}%</span>
    </div>
  );
}

function Avatar({ name }: { name: string }) {
  const initials = name.split(' ').map(n => n[0]).join('').slice(0, 2);
  const colors = ['#1a3a80', '#1a5040', '#3a1a60', '#4a1a20', '#1a4040'];
  const ci = name.charCodeAt(0) % colors.length;
  return (
    <div style={{
      width: 32, height: 32, borderRadius: '50%',
      background: colors[ci], border: '1px solid #2a3a60',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 11, fontWeight: 700, color: '#a0b8e0', flexShrink: 0,
    }}>
      {initials}
    </div>
  );
}

export default function TrustedUsersScreen({ navigate }: { navigate: NavigateFn }) {
  const [users, setUsers] = useState<UserProfile[]>(FALLBACK_USERS);
  const [live, setLive] = useState(false);
  const [stats, setStats] = useState({ total: FALLBACK_USERS.length, enrolled: 6, suspended: 1, avg_quality: 93 });

  useEffect(() => {
    let cancelled = false;
    listUsers()
      .then(d => {
        if (cancelled) return;
        if (d.users.length > 0) setUsers(d.users);
        setStats({ total: d.total, enrolled: d.enrolled, suspended: d.suspended, avg_quality: d.avg_quality });
        setLive(true);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  return (
    <div>
      <PageHeader title="Trusted User Profiles" subtitle="Enrolled voice identities authorized for verified access.">
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
          color: live ? '#20d870' : '#f5a020',
          background: live ? '#082010' : '#2a1e06',
          border: `1px solid ${live ? '#20d87050' : '#f5a02050'}`,
          padding: '2px 8px', borderRadius: 4,
        }}>
          {live ? '● LIVE REGISTRY' : '○ DEMO DATA'}
        </span>
        <Btn onClick={() => navigate('register-user')} size="sm">+ Register User</Btn>
      </PageHeader>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
        {[
          { label: 'Total Enrolled', value: stats.total },
          { label: 'Active Profiles', value: stats.enrolled, color: '#20d870' },
          { label: 'Suspended', value: stats.suspended, color: '#f5a020' },
          { label: 'Avg. Quality', value: `${stats.avg_quality}%`, color: '#4080f8' },
        ].map(s => (
          <div key={s.label} style={{
            background: '#0e1233', border: '1px solid #18234a', borderRadius: 10, padding: '14px 18px',
          }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>{s.label}</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 24, fontWeight: 700, color: s.color ?? '#d5dffa' }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Table */}
      <Card>
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 90px 100px 80px',
          padding: '8px 20px', borderBottom: '1px solid #18234a',
        }}>
          {['User', 'Role / Department', 'Voice Profile', 'Quality', 'Status', 'Actions'].map(h => (
            <span key={h} style={{ fontSize: 10, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase' }}>{h}</span>
          ))}
        </div>
        {users.map((user, i) => (
          <div
            key={user.id}
            style={{
              display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 90px 100px 80px',
              padding: '12px 20px', alignItems: 'center',
              borderBottom: i < users.length - 1 ? '1px solid #0e1838' : 'none',
              transition: 'background 0.12s',
            }}
            onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.background = '#0c1030'}
            onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.background = 'transparent'}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Avatar name={user.name} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 500, color: '#d5dffa' }}>{user.name}</div>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#3a4e78' }}>{user.id}</div>
              </div>
            </div>
            <div>
              <div style={{ fontSize: 13, color: '#d5dffa' }}>{user.role}</div>
              <div style={{ fontSize: 11, color: '#3a4e78', marginTop: 2 }}>{user.dept}</div>
            </div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#6280b8' }}>{user.profile}</div>
            <QualityBar value={user.quality} />
            <span title="Demo only: the backend tracks enrollment, not live presence">
              <ServiceBadge status={user.status === 'Active' ? 'ONLINE' : 'OFFLINE'} />
            </span>
            <span title="Demo only: no user-management endpoint exists">
              <button
                disabled
                style={{
                  fontSize: 11, color: '#3a4e78', background: 'transparent',
                  border: '1px dashed #28384a', borderRadius: 5, padding: '4px 10px',
                  cursor: 'not-allowed',
                }}>
                Manage
              </button>
            </span>
          </div>
        ))}
        {users.length === 0 && (
          <div style={{ padding: '32px', textAlign: 'center', color: '#3a4e78', fontSize: 13 }}>
            No enrolled profiles yet — register the first voice profile.
          </div>
        )}
      </Card>

      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginTop: 14,
        padding: '10px 14px', borderRadius: 8, background: '#0a1428', border: '1px solid #18234a',
      }}>
        <DemoBadge />
        <span style={{ fontSize: 11, color: '#6280b8' }}>
          Name / profile / enrollment rows are live backend data. Presence status and Manage actions are demo-only —
          the backend is a fraud-detection pipeline, not a user-management platform.
        </span>
      </div>
    </div>
  );
}
