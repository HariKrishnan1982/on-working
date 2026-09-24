import { useEffect, useState } from 'react';
import type { NavigateFn, Selection } from '../App';
import { PageHeader, RiskBadge, ActionBadge, Card } from '../components/ui';
import { listAlerts, type AlertItem } from '../lib/api';

const FALLBACK_ALERTS: AlertItem[] = [
  { id: 'ALT-0091', session: 'CALL-1042', title: 'Possible Voice Cloning Attack', risk: 92, action: 'BLOCKED', severity: 'Critical', time: '10:42:17', resolved: false },
  { id: 'ALT-0090', session: 'CALL-1038', title: 'Suspicious Financial Request', risk: 76, action: 'MFA', severity: 'High', time: '10:39:11', resolved: false },
  { id: 'ALT-0089', session: 'CALL-1035', title: 'Behavioral Pattern Anomaly', risk: 63, action: 'MFA', severity: 'High', time: '10:34:55', resolved: false },
  { id: 'ALT-0088', session: 'CALL-1031', title: 'Identity Mismatch Detected', risk: 52, action: 'CALLBACK', severity: 'Medium', time: '10:28:30', resolved: true },
  { id: 'ALT-0087', session: 'CALL-1028', title: 'Adversarial Input Detected', risk: 81, action: 'BLOCKED', severity: 'Critical', time: '10:22:41', resolved: false },
  { id: 'ALT-0086', session: 'CALL-1024', title: 'Context Fraud Indicator', risk: 67, action: 'MFA', severity: 'High', time: '10:15:08', resolved: true },
  { id: 'ALT-0085', session: 'CALL-1020', title: 'Low-Confidence Voice Match', risk: 38, action: 'MFA', severity: 'Medium', time: '10:08:22', resolved: true },
];

const FILTERS = ['All', 'Critical', 'High', 'Medium', 'Resolved'] as const;
type Filter = typeof FILTERS[number];

function severityColor(sev: string) {
  if (sev === 'Critical') return '#f03838';
  if (sev === 'High') return '#f07228';
  if (sev === 'Medium') return '#f5a020';
  return '#6280b8';
}

export default function AlertsScreen({ navigate: _navigate, selection }: { navigate: NavigateFn; selection: Selection }) {
  const [filter, setFilter] = useState<Filter>('All');
  const [alerts, setAlerts] = useState<AlertItem[]>(FALLBACK_ALERTS);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    listAlerts()
      .then(d => {
        if (cancelled) return;
        // A reachable backend returning zero alerts is an honest empty state,
        // not a reason to keep showing demo rows.
        setAlerts(d.alerts);
        setLive(true);
      })
      .catch(() => {
        if (cancelled) return;
        setAlerts(FALLBACK_ALERTS);
        setLive(false);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const filtered = alerts.filter(a => {
    if (filter === 'All') return true;
    if (filter === 'Resolved') return a.resolved;
    return a.severity === filter && !a.resolved;
  });

  const counts = {
    Critical: alerts.filter(a => a.severity === 'Critical' && !a.resolved).length,
    High: alerts.filter(a => a.severity === 'High' && !a.resolved).length,
    Medium: alerts.filter(a => a.severity === 'Medium' && !a.resolved).length,
  };

  return (
    <div>
      <PageHeader
        title="Security Alerts"
        subtitle={`${alerts.filter(a => !a.resolved).length} active alerts requiring attention.`}
      >
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
          color: live ? '#20d870' : '#f5a020',
          background: live ? '#082010' : '#2a1e06',
          border: `1px solid ${live ? '#20d87050' : '#f5a02050'}`,
          padding: '2px 8px', borderRadius: 4,
        }}>
          {live ? '● LIVE' : '○ DEMO DATA'}
        </span>
        {loading && <span style={{ fontSize: 11, color: '#6280b8' }}>Loading…</span>}
      </PageHeader>

      {/* Filter bar */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 20 }}>
        {FILTERS.map(f => {
          const isActive = filter === f;
          const count = f === 'Critical' ? counts.Critical : f === 'High' ? counts.High : f === 'Medium' ? counts.Medium : null;
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '6px 14px', borderRadius: 6, border: 'none',
                fontSize: 12, fontWeight: isActive ? 600 : 400, cursor: 'pointer',
                background: isActive ? '#0f2050' : 'transparent',
                color: isActive ? '#90b8f8' : '#5070a0',
                outline: isActive ? '1px solid #2a4080' : '1px solid transparent',
                transition: 'all 0.15s',
              }}
            >
              {f}
              {count !== null && (
                <span style={{
                  fontSize: 10, fontWeight: 700,
                  background: f === 'Critical' ? '#2a0808' : f === 'High' ? '#2a1408' : '#2a1e06',
                  color: f === 'Critical' ? '#f03838' : f === 'High' ? '#f07228' : '#f5a020',
                  padding: '0 5px', borderRadius: 10, minWidth: 18, textAlign: 'center',
                }}>
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Alert list */}
      <Card>
        {!live && !loading && (
          <div style={{ padding: '8px 20px', fontSize: 11, color: '#f5a020', background: '#2a1e06', borderBottom: '1px solid #0e1838' }}>
            Demo data — backend unreachable. Live HIGH/CRITICAL sessions will appear here.
          </div>
        )}
        {live && !loading && alerts.length === 0 && (
          <div style={{ padding: '32px', textAlign: 'center', color: '#3a4e78', fontSize: 13 }}>
            No HIGH/CRITICAL alerts — all analyzed calls are within safe bounds.
          </div>
        )}
        <div style={{
          display: 'grid', gridTemplateColumns: '100px 1fr 80px 100px 130px 80px',
          padding: '8px 20px', borderBottom: '1px solid #18234a',
        }}>
          {['Alert ID', 'Threat', 'Risk', 'Session', 'Action', 'Status'].map(h => (
            <span key={h} style={{ fontSize: 10, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase' }}>{h}</span>
          ))}
        </div>
        {filtered.map((alert, i) => (
          <div
            key={alert.id}
            onClick={() => selection.openSession(alert.session)}
            style={{
              display: 'grid', gridTemplateColumns: '100px 1fr 80px 100px 130px 80px',
              padding: '12px 20px', cursor: 'pointer', transition: 'background 0.12s',
              borderBottom: i < filtered.length - 1 ? '1px solid #0e1838' : 'none',
              alignItems: 'center',
              borderLeft: `3px solid ${alert.resolved ? '#18234a' : severityColor(alert.severity)}`,
            }}
            onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.background = '#0c1030'}
            onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.background = 'transparent'}
          >
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3a4e78' }}>{alert.id}</span>
            <div>
              <div style={{ fontSize: 13, fontWeight: 500, color: '#d5dffa', marginBottom: 2 }}>{alert.title}</div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3a4e78' }}>{alert.time}</div>
            </div>
            <RiskBadge score={alert.risk} />
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#6280b8' }}>{alert.session}</span>
            <ActionBadge action={alert.action} />
            <span style={{
              fontSize: 11, fontWeight: 600,
              color: alert.resolved ? '#20d870' : severityColor(alert.severity),
            }}>
              {alert.resolved ? 'Resolved' : alert.severity}
            </span>
          </div>
        ))}
        {filtered.length === 0 && (
          <div style={{ padding: '32px', textAlign: 'center', color: '#3a4e78', fontSize: 13 }}>
            No alerts match the selected filter.
          </div>
        )}
      </Card>
    </div>
  );
}
