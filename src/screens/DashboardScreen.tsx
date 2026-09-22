import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import type { NavigateFn } from '../App';
import { MetricCard, PageHeader, RiskBadge, ActionBadge, Card, SectionTitle } from '../components/ui';

const riskChartData = [
  { time: '10:00', risk: 18, calls: 3 },
  { time: '10:05', risk: 24, calls: 5 },
  { time: '10:10', risk: 31, calls: 4 },
  { time: '10:15', risk: 22, calls: 6 },
  { time: '10:20', risk: 48, calls: 8 },
  { time: '10:25', risk: 72, calls: 7 },
  { time: '10:30', risk: 86, calls: 9 },
  { time: '10:35', risk: 64, calls: 7 },
  { time: '10:40', risk: 92, calls: 8 },
  { time: '10:42', risk: 78, calls: 6 },
  { time: '10:44', risk: 55, calls: 5 },
  { time: '10:46', risk: 38, calls: 4 },
];

const recentEvents = [
  { time: '10:42', caller: 'User 104', risk: 92, detection: 'Voice Clone', action: 'BLOCKED' },
  { time: '10:39', caller: 'User 087', risk: 68, detection: 'Suspicious Context', action: 'MFA' },
  { time: '10:31', caller: 'User 221', risk: 24, detection: 'Verified', action: 'ALLOWED' },
  { time: '10:25', caller: 'User 112', risk: 81, detection: 'Deepfake Signal', action: 'BLOCKED' },
  { time: '10:18', caller: 'User 345', risk: 44, detection: 'Behavior Anomaly', action: 'MFA' },
  { time: '10:11', caller: 'User 078', risk: 17, detection: 'Verified', action: 'ALLOWED' },
];

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  const v = payload[0].value;
  const color = v >= 80 ? '#f03838' : v >= 60 ? '#f07228' : v >= 30 ? '#f5a020' : '#20d870';
  return (
    <div style={{ background: '#0e1233', border: '1px solid #28386a', borderRadius: 8, padding: '8px 12px' }}>
      <div style={{ fontSize: 11, color: '#6280b8', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 700, color, fontFamily: "'JetBrains Mono', monospace" }}>
        Risk: {v}
      </div>
    </div>
  );
}

export default function DashboardScreen({ navigate }: { navigate: NavigateFn }) {
  return (
    <div>
      <PageHeader
        title="Security Overview"
        subtitle="Real-time monitoring of protected voice interactions."
      />

      {/* KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14, marginBottom: 24 }}>
        <MetricCard label="Active Calls" value={12} sub="Live sessions" accent="#4080f8" onClick={() => navigate('live-calls')} />
        <MetricCard label="Calls Analyzed" value="1,248" sub="Last 24h" />
        <MetricCard label="Threats Detected" value={27} sub="Today" accent="#f07228" />
        <MetricCard label="Calls Blocked" value={9} sub="Today" accent="#f03838" />
        <MetricCard
          label="Gateway Status"
          value="ONLINE"
          sub="All systems nominal"
          accent="#20d870"
        />
      </div>

      {/* Chart */}
      <Card style={{ padding: '20px 24px', marginBottom: 24 }}>
        <SectionTitle>Real-Time Risk Monitoring</SectionTitle>
        <div style={{ height: 200 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={riskChartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="riskGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#4080f8" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#4080f8" stopOpacity={0.03} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#18234a" vertical={false} />
              <XAxis
                dataKey="time"
                tick={{ fill: '#3a4e78', fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}
                axisLine={{ stroke: '#18234a' }} tickLine={false}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fill: '#3a4e78', fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}
                axisLine={false} tickLine={false}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone" dataKey="risk" stroke="#4080f8" strokeWidth={2}
                fill="url(#riskGrad)" dot={false} activeDot={{ r: 4, fill: '#4080f8', stroke: '#0e1233', strokeWidth: 2 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        {/* Risk bands legend */}
        <div style={{ display: 'flex', gap: 20, marginTop: 12 }}>
          {[
            { label: 'Critical ≥80', color: '#f03838' },
            { label: 'High 60–79', color: '#f07228' },
            { label: 'Medium 30–59', color: '#f5a020' },
            { label: 'Low <30', color: '#20d870' },
          ].map(b => (
            <div key={b.label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <div style={{ width: 8, height: 8, borderRadius: 2, background: b.color }} />
              <span style={{ fontSize: 11, color: '#3a4e78' }}>{b.label}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* Recent Events Table */}
      <Card>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #18234a', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <SectionTitle>Recent Security Events</SectionTitle>
          <button onClick={() => navigate('alerts')} style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            fontSize: 12, color: '#4080f8',
          }}>View All Alerts →</button>
        </div>
        {/* Header */}
        <div style={{
          display: 'grid', gridTemplateColumns: '80px 1fr 80px 1fr 120px',
          padding: '8px 20px', borderBottom: '1px solid #0e1838',
        }}>
          {['Time', 'Caller', 'Risk', 'Detection', 'Action'].map(h => (
            <span key={h} style={{ fontSize: 10, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase' }}>{h}</span>
          ))}
        </div>
        {recentEvents.map((ev, i) => (
          <div
            key={i}
            onClick={() => navigate('alert-detail')}
            style={{
              display: 'grid', gridTemplateColumns: '80px 1fr 80px 1fr 120px',
              padding: '11px 20px',
              borderBottom: i < recentEvents.length - 1 ? '1px solid #0e1838' : 'none',
              cursor: 'pointer', transition: 'background 0.12s',
              alignItems: 'center',
            }}
            onMouseEnter={e => (e.currentTarget as HTMLDivElement).style.background = '#0c1030'}
            onMouseLeave={e => (e.currentTarget as HTMLDivElement).style.background = 'transparent'}
          >
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#3a4e78' }}>{ev.time}</span>
            <span style={{ fontSize: 13, color: '#d5dffa' }}>{ev.caller}</span>
            <span><RiskBadge score={ev.risk} /></span>
            <span style={{ fontSize: 13, color: '#8090b8' }}>{ev.detection}</span>
            <span><ActionBadge action={ev.action} /></span>
          </div>
        ))}
      </Card>
    </div>
  );
}
