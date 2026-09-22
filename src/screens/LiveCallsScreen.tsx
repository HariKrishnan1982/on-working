import type { NavigateFn } from '../App';
import { PageHeader, RiskBadge, ActionBadge, riskColor, Card } from '../components/ui';

const liveCalls = [
  {
    id: 'CALL-1042', caller: 'EMP-1042', duration: '02:43',
    risk: 92, identity: 8, deepfake: 87, context: 91, behavior: 74,
    action: 'BLOCKED', status: 'CRITICAL',
  },
  {
    id: 'CALL-1038', caller: 'EMP-1038', duration: '05:12',
    risk: 76, identity: 61, deepfake: 42, context: 78, behavior: 55,
    action: 'MFA', status: 'HIGH',
  },
  {
    id: 'CALL-1041', caller: 'EMP-1041', duration: '01:08',
    risk: 22, identity: 94, deepfake: 4, context: 15, behavior: 18,
    action: 'ALLOWED', status: 'LOW',
  },
  {
    id: 'CALL-1039', caller: 'EMP-1039', duration: '03:55',
    risk: 44, identity: 78, deepfake: 22, context: 38, behavior: 42,
    action: 'ALLOWED', status: 'MEDIUM',
  },
  {
    id: 'CALL-1035', caller: 'EMP-1035', duration: '08:21',
    risk: 63, identity: 55, deepfake: 38, context: 66, behavior: 60,
    action: 'MFA', status: 'HIGH',
  },
  {
    id: 'CALL-1033', caller: 'EMP-1033', duration: '04:47',
    risk: 18, identity: 97, deepfake: 3, context: 12, behavior: 14,
    action: 'ALLOWED', status: 'LOW',
  },
];

function ScoreBar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ flex: 1, height: 4, background: '#18234a', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${value}%`, background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6280b8', width: 24, textAlign: 'right' }}>{value}</span>
    </div>
  );
}

function PulsingDot({ color }: { color: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <span style={{
        width: 7, height: 7, borderRadius: '50%', background: color,
        display: 'inline-block', boxShadow: `0 0 0 2px ${color}30`,
      }} />
    </span>
  );
}

export default function LiveCallsScreen({ navigate }: { navigate: NavigateFn }) {
  return (
    <div>
      <PageHeader title="Live Call Monitoring" subtitle="Active voice sessions under real-time security analysis.">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#20d870', fontWeight: 600 }}>
          <PulsingDot color="#20d870" />
          {liveCalls.length} Active Sessions
        </div>
      </PageHeader>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
        {liveCalls.map(call => {
          const rc = riskColor(call.risk);
          return (
            <Card key={call.id} style={{ padding: '18px 20px' }}>
              {/* Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
                <div>
                  <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, fontWeight: 600, color: '#d5dffa' }}>{call.id}</div>
                  <div style={{ fontSize: 12, color: '#6280b8', marginTop: 2 }}>Caller: {call.caller}</div>
                </div>
                <ActionBadge action={call.action} />
              </div>

              {/* Duration */}
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
                <div style={{ fontSize: 12, color: '#6280b8' }}>Duration</div>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#d5dffa' }}>{call.duration}</div>
              </div>

              {/* Risk score large */}
              <div style={{
                padding: '10px 14px', borderRadius: 8,
                background: `${rc}12`, border: `1px solid ${rc}30`,
                marginBottom: 14, display: 'flex', alignItems: 'center', gap: 12,
              }}>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 28, fontWeight: 700, color: rc, lineHeight: 1 }}>{call.risk}</div>
                <div>
                  <div style={{ fontSize: 10, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Risk Score</div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: rc, letterSpacing: '0.06em' }}>{call.status}</div>
                </div>
              </div>

              {/* Score bars */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginBottom: 16 }}>
                {[
                  { label: 'Identity Score', value: call.identity, color: '#4080f8' },
                  { label: 'Deepfake Prob.', value: call.deepfake, color: riskColor(call.deepfake) },
                  { label: 'Context Risk', value: call.context, color: riskColor(call.context) },
                  { label: 'Behavior Score', value: call.behavior, color: riskColor(call.behavior) },
                ].map(s => (
                  <div key={s.label}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                      <span style={{ fontSize: 11, color: '#3a4e78' }}>{s.label}</span>
                    </div>
                    <ScoreBar value={s.value} color={s.color} />
                  </div>
                ))}
              </div>

              {/* View button */}
              <button
                onClick={() => navigate('session-detail')}
                style={{
                  width: '100%', padding: '8px',
                  background: '#0f2050', border: '1px solid #2a4080',
                  borderRadius: 6, color: '#6090d8', fontSize: 13, fontWeight: 500,
                  cursor: 'pointer', transition: 'all 0.15s',
                }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLButtonElement).style.background = '#162860';
                  (e.currentTarget as HTMLButtonElement).style.color = '#90b8f8';
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLButtonElement).style.background = '#0f2050';
                  (e.currentTarget as HTMLButtonElement).style.color = '#6090d8';
                }}
              >
                View Session →
              </button>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
