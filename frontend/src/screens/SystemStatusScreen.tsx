import { useEffect, useState } from 'react';
import type { NavigateFn } from '../App';
import { PageHeader, Card, SectionTitle } from '../components/ui';
import { getSystemStatus, type SystemStatusResponse } from '../lib/api';

const FALLBACK_SERVICES = [
  { name: 'Gateway API', status: 'ONLINE', latency: 1, version: 'v0.2.0', uptime: 'running' },
  { name: 'Voice Engine (Preprocess + VAD)', status: 'ONLINE', latency: 42, version: 'silero-vad-6.2.2', uptime: 'ready' },
  { name: 'Anti-Spoofing (AASIST)', status: 'ONLINE', latency: 38, version: 'aasist-asvspoof2019-v0', uptime: 'ready' },
  { name: 'Speaker Verification (ECAPA-TDNN)', status: 'ONLINE', latency: 55, version: 'ecapa-tdnn-voxceleb-v0', uptime: 'ready' },
  { name: 'ASR & Intent (Faster-Whisper)', status: 'OFFLINE', latency: 0, version: 'faster-whisper-base', uptime: 'missing weights' },
  { name: 'Risk Engine (rules.yaml)', status: 'ONLINE', latency: 1, version: 'rules', uptime: 'ready' },
  { name: 'PostgreSQL Audit Chain', status: 'OFFLINE', latency: 0, version: 'PG16', uptime: 'unreachable' },
  { name: 'Fabric Bridge (Blockchain)', status: 'OFFLINE', latency: 0, version: 'REST v1', uptime: 'unreachable' },
  { name: 'Enrollment Store (Encrypted)', status: 'ONLINE', latency: 2, version: 'Fernet AES-128-CBC', uptime: 'ready' },
];

function StatusDot({ status }: { status: string }) {
  const color = status === 'ONLINE' ? '#20d870' : status === 'DEGRADED' ? '#f5a020' : '#f03838';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 7, height: 7, borderRadius: '50%', background: color, boxShadow: `0 0 5px ${color}70` }} />
      <span style={{ fontSize: 12, fontWeight: 600, color, letterSpacing: '0.04em' }}>{status}</span>
    </div>
  );
}

function LatencyBar({ ms }: { ms: number | null | undefined }) {
  if (ms == null) return <span style={{ fontSize: 11, color: '#3a4e78' }}>—</span>;
  const pct = Math.min(ms / 200, 1) * 100;
  const color = ms < 50 ? '#20d870' : ms < 100 ? '#f5a020' : '#f07228';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ width: 60, height: 3, background: '#18234a', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6280b8' }}>
        {ms < 10 ? ms.toFixed(1) : Math.round(ms)}ms
      </span>
    </div>
  );
}

function fmtCount(n: number | null | undefined): string {
  return n == null ? '— (db offline)' : String(n);
}

export default function SystemStatusScreen({ navigate: _navigate }: { navigate: NavigateFn }) {
  const [data, setData] = useState<SystemStatusResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSystemStatus().then(d => { if (!cancelled) setData(d); }).catch(() => {});
    const id = setInterval(() => {
      getSystemStatus().then(d => { if (!cancelled) setData(d); }).catch(() => {});
    }, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  const services = data?.services ?? FALLBACK_SERVICES;
  const apiMetrics = data?.apiMetrics ?? [
    { endpoint: 'GET /health', method: 'GET', status: 200 },
    { endpoint: 'GET /api/v1/sessions', method: 'GET', status: 200 },
    { endpoint: 'GET /api/v1/audit', method: 'GET', status: 200 },
  ];
  const stack = data?.stack ?? [
    { name: 'Python', version: '3.11' },
    { name: 'FastAPI', version: '0.141' },
    { name: 'PyTorch', version: '2.9 CPU' },
    { name: 'Hyperledger Fabric', version: '2.5' },
    { name: 'PostgreSQL', version: '16' },
    { name: 'React', version: '19' },
  ];
  const onlineCount = services.filter(s => s.status === 'ONLINE').length;
  const allOnline = onlineCount === services.length;
  const checkedAt = data ? new Date(data.backend.timestamp).toLocaleTimeString('en-US', { hour12: false }) : null;

  return (
    <div>
      <PageHeader title="System Status" subtitle="Real-time health monitoring of all VoiceShield components.">
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
          color: data ? '#20d870' : '#f5a020',
          background: data ? '#082010' : '#2a1e06',
          border: `1px solid ${data ? '#20d87050' : '#f5a02050'}`,
          padding: '2px 8px', borderRadius: 4,
        }}>
          {data ? '● LIVE PROBES' : '○ DEMO DATA'}
        </span>
      </PageHeader>

      {/* Overall banner */}
      <div style={{
        padding: '14px 20px', borderRadius: 10, marginBottom: 24,
        background: allOnline ? '#082010' : '#2a1408',
        border: `1px solid ${allOnline ? '#20d87050' : '#f0723040'}`,
        display: 'flex', alignItems: 'center', gap: 14,
      }}>
        <div style={{
          width: 42, height: 42, borderRadius: '50%',
          background: allOnline ? '#0a3018' : '#2a1800',
          border: `2px solid ${allOnline ? '#20d870' : '#f07228'}`,
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          {allOnline ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#20d870" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f07228" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          )}
        </div>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: allOnline ? '#20d870' : '#f07228', marginBottom: 2 }}>
            {allOnline ? 'All Systems Operational' : 'Partial Degradation Detected'}
          </div>
          <div style={{ fontSize: 12, color: '#6280b8' }}>
            {services.length} services monitored
            {checkedAt ? ` · Last checked: ${checkedAt} UTC` : ' · backend unreachable'}
            {data ? ` · DB: ${data.backend.database} · Fabric: ${data.backend.fabric_bridge}` : ''}
          </div>
        </div>
        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 700, color: allOnline ? '#20d870' : '#f07228' }}>
            {onlineCount}/{services.length}
          </div>
          <div style={{ fontSize: 11, color: '#3a4e78' }}>services online</div>
        </div>
      </div>

      {/* Fabric / outbox strip — real anchor counts, never faked green */}
      <Card style={{ padding: '12px 18px', marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: '#3a4e78' }}>
            Fabric bridge: <span style={{
              fontFamily: "'JetBrains Mono', monospace", fontWeight: 700,
              color: data?.backend.fabric_bridge === 'online' ? '#20d870' : '#f03838',
            }}>{data ? data.backend.fabric_bridge.toUpperCase() : 'UNKNOWN (offline demo)'}</span>
          </span>
          <span style={{ fontSize: 11, color: '#3a4e78' }}>
            Outbox anchor_pending: <span style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, color: '#f5a020' }}>{data ? fmtCount(data.backend.outbox_pending) : '—'}</span>
          </span>
          <span style={{ fontSize: 11, color: '#3a4e78' }}>
            Outbox anchored: <span style={{ fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, color: '#20d870' }}>{data ? fmtCount(data.backend.outbox_anchored) : '—'}</span>
          </span>
          <span style={{ fontSize: 11, color: '#3a4e78' }}>Live Fabric network deferred — OFFLINE here is the true state, not an error.</span>
        </div>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 20 }}>
        {/* Services table */}
        <Card>
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 100px 80px 80px 90px',
            padding: '8px 18px', borderBottom: '1px solid #18234a',
          }}>
            {['Service', 'Status', 'Latency', 'Version', 'Uptime'].map(h => (
              <span key={h} style={{ fontSize: 10, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase' }}>{h}</span>
            ))}
          </div>
          {services.map((svc, i) => (
            <div
              key={svc.name}
              style={{
                display: 'grid', gridTemplateColumns: '1fr 100px 80px 80px 90px',
                padding: '11px 18px', alignItems: 'center',
                borderBottom: i < services.length - 1 ? '1px solid #0e1838' : 'none',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{
                  width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                  background: svc.status === 'ONLINE' ? '#20d870' : '#f03838',
                  boxShadow: svc.status === 'ONLINE' ? '0 0 4px #20d87070' : 'none',
                }} />
                <span style={{ fontSize: 13, color: '#d5dffa' }}>{svc.name}</span>
              </div>
              <StatusDot status={svc.status} />
              <LatencyBar ms={svc.latency} />
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3a4e78' }}>{svc.version}</span>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6280b8' }}>{svc.uptime}</span>
            </div>
          ))}
        </Card>

        {/* API health + stack */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card style={{ padding: '16px 18px' }}>
            <SectionTitle>API Health</SectionTitle>
            {apiMetrics.map(m => (
              <div key={m.endpoint} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '7px 0', borderBottom: '1px solid #0e1838',
              }}>
                <span style={{ fontSize: 12, color: '#3a4e78' }}>{m.endpoint}</span>
                <span style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 12, fontWeight: 600,
                  color: m.status === 200 ? '#20d870' : '#f03838',
                }}>{m.status}</span>
              </div>
            ))}
            <div style={{ fontSize: 10, color: '#3a4e78', marginTop: 8 }}>
              Per-endpoint latencies are not measured server-side, so none are shown.
            </div>
          </Card>

          <Card style={{ padding: '16px 18px' }}>
            <SectionTitle>Technology Stack</SectionTitle>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {stack.map(item => (
                <span key={item.name} style={{
                  fontSize: 11, color: '#6280b8', background: '#080e28',
                  border: '1px solid #18234a', padding: '2px 8px', borderRadius: 4,
                  fontFamily: "'JetBrains Mono', monospace",
                }}>{item.name} {item.version}</span>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
