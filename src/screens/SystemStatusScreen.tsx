import type { NavigateFn } from '../App';
import { PageHeader, Card, SectionTitle } from '../components/ui';

interface Service {
  name: string;
  status: 'ONLINE' | 'OFFLINE' | 'DEGRADED';
  latency?: number;
  version?: string;
  uptime?: string;
}

const services: Service[] = [
  { name: 'Voice Engine', status: 'ONLINE', latency: 42, version: 'v3.2.1', uptime: '14d 06h' },
  { name: 'Deepfake Detector', status: 'ONLINE', latency: 88, version: 'v2.8.4', uptime: '14d 06h' },
  { name: 'Context Agent', status: 'ONLINE', latency: 31, version: 'v1.6.0', uptime: '14d 06h' },
  { name: 'Behavior Agent', status: 'ONLINE', latency: 27, version: 'v1.4.2', uptime: '14d 06h' },
  { name: 'Adversarial Agent', status: 'ONLINE', latency: 55, version: 'v1.1.8', uptime: '14d 06h' },
  { name: 'MCP Server', status: 'ONLINE', latency: 8, version: 'v4.0.2', uptime: '14d 06h' },
  { name: 'Risk Engine', status: 'ONLINE', latency: 12, version: 'v2.3.7', uptime: '14d 06h' },
  { name: 'PostgreSQL', status: 'ONLINE', latency: 4, version: '16.3', uptime: '14d 06h' },
  { name: 'Hyperledger Fabric', status: 'ONLINE', latency: 95, version: 'v2.5.4', uptime: '14d 06h' },
  { name: 'JWT Auth Service', status: 'ONLINE', latency: 6, version: 'v1.9.0', uptime: '14d 06h' },
];

const apiMetrics = [
  { label: 'API Gateway', status: 'Healthy' as const, value: '● Healthy' },
  { label: 'Avg Response Time', value: '142 ms' },
  { label: 'Active Connections', value: '37' },
  { label: 'Requests / Min', value: '284' },
  { label: 'Error Rate', value: '0.02%' },
  { label: 'TLS Version', value: 'TLS 1.3' },
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

function LatencyBar({ ms }: { ms: number }) {
  const pct = Math.min(ms / 200, 1) * 100;
  const color = ms < 50 ? '#20d870' : ms < 100 ? '#f5a020' : '#f07228';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ width: 60, height: 3, background: '#18234a', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6280b8' }}>{ms}ms</span>
    </div>
  );
}

export default function SystemStatusScreen({ navigate: _navigate }: { navigate: NavigateFn }) {
  const allOnline = services.every(s => s.status === 'ONLINE');

  return (
    <div>
      <PageHeader title="System Status" subtitle="Real-time health monitoring of all VoiceShield components." />

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
            {services.length} services monitored · Last checked: 10:46:52 UTC
          </div>
        </div>
        <div style={{ marginLeft: 'auto', textAlign: 'right' }}>
          <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 700, color: '#20d870' }}>100%</div>
          <div style={{ fontSize: 11, color: '#3a4e78' }}>uptime this month</div>
        </div>
      </div>

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
              {svc.latency !== undefined ? <LatencyBar ms={svc.latency} /> : <span />}
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
              <div key={m.label} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '7px 0', borderBottom: '1px solid #0e1838',
              }}>
                <span style={{ fontSize: 12, color: '#3a4e78' }}>{m.label}</span>
                <span style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 12, fontWeight: 600,
                  color: m.label === 'API Gateway' ? '#20d870' : '#d5dffa',
                }}>{m.value}</span>
              </div>
            ))}
          </Card>

          <Card style={{ padding: '16px 18px' }}>
            <SectionTitle>Technology Stack</SectionTitle>
            {[
              { cat: 'Backend', items: ['Python / FastAPI', 'PyTorch', 'Wav2Vec2', 'RawNet2', 'Librosa'] },
              { cat: 'Security', items: ['JWT / RBAC', 'TLS 1.3', 'MCP Server'] },
              { cat: 'Data', items: ['PostgreSQL 16', 'Hyperledger Fabric 2.5'] },
              { cat: 'Frontend', items: ['React 19', 'Recharts'] },
              { cat: 'Infrastructure', items: ['Docker', 'Multi-agent Python'] },
            ].map(g => (
              <div key={g.cat} style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 9, fontWeight: 700, color: '#2a3a60', letterSpacing: '0.12em', textTransform: 'uppercase', marginBottom: 5 }}>{g.cat}</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {g.items.map(item => (
                    <span key={item} style={{
                      fontSize: 11, color: '#6280b8', background: '#080e28',
                      border: '1px solid #18234a', padding: '2px 8px', borderRadius: 4,
                    }}>{item}</span>
                  ))}
                </div>
              </div>
            ))}
          </Card>
        </div>
      </div>
    </div>
  );
}
