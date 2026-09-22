import type { NavigateFn } from '../App';
import { BackButton, RiskGauge, Card, SectionTitle } from '../components/ui';

function AgentCard({
  title, metrics, status,
}: {
  title: string;
  metrics: { label: string; value: string; color?: string }[];
  status: 'VERIFIED' | 'SUSPICIOUS' | 'UNUSUAL' | 'FLAGGED';
}) {
  const statusColors: Record<string, { color: string; bg: string }> = {
    VERIFIED:   { color: '#20d870', bg: '#082010' },
    SUSPICIOUS: { color: '#f07228', bg: '#2a1408' },
    UNUSUAL:    { color: '#f5a020', bg: '#2a1e06' },
    FLAGGED:    { color: '#f03838', bg: '#2a0808' },
  };
  const sc = statusColors[status] ?? { color: '#6280b8', bg: '#0e1233' };

  return (
    <div style={{
      background: '#0b1028', border: '1px solid #18234a',
      borderRadius: 10, padding: '14px 16px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase' }}>{title}</div>
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.06em',
          color: sc.color, background: sc.bg, border: `1px solid ${sc.color}40`,
          padding: '2px 7px', borderRadius: 4,
        }}>{status}</span>
      </div>
      {metrics.map(m => (
        <div key={m.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <span style={{ fontSize: 12, color: '#6280b8' }}>{m.label}</span>
          <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, fontWeight: 600, color: m.color ?? '#d5dffa' }}>{m.value}</span>
        </div>
      ))}
    </div>
  );
}

function EvidenceRow({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      padding: '8px 0', borderBottom: '1px solid #0e1838',
    }}>
      <span style={{ fontSize: 12, color: '#6280b8' }}>{label}</span>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, fontWeight: 600, color: color ?? '#d5dffa' }}>{value}</span>
    </div>
  );
}

function McpTool({ name }: { name: string }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 7,
      padding: '5px 10px', borderRadius: 6,
      background: '#0a1428', border: '1px solid #1a2e50',
    }}>
      <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#4080f8' }} />
      <span style={{ fontSize: 12, color: '#7090c0' }}>{name}</span>
    </div>
  );
}

export default function SessionDetailScreen({ navigate }: { navigate: NavigateFn }) {
  return (
    <div>
      <BackButton onClick={() => navigate('live-calls')} label="Back to Live Calls" />

      {/* Session header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        marginBottom: 24,
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 20, fontWeight: 700, color: '#d5dffa' }}>CALL SESSION #CALL-1042</span>
            <span style={{
              fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
              color: '#4080f8', background: '#0a1838', border: '1px solid #2040a0',
              padding: '3px 8px', borderRadius: 4,
            }}>
              ● ANALYSIS ACTIVE
            </span>
          </div>
          <div style={{ fontSize: 13, color: '#6280b8' }}>Real-time multi-agent voice security analysis in progress</div>
        </div>
        <button onClick={() => navigate('alert-detail')} style={{
          padding: '8px 16px', background: '#2a0808', border: '1px solid #f0383880',
          borderRadius: 6, color: '#f03838', fontSize: 12, fontWeight: 600,
          cursor: 'pointer',
        }}>
          View Alert →
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 20 }}>
        {/* Left: caller info + gauge */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Caller info */}
          <Card style={{ padding: '16px 18px' }}>
            <SectionTitle>Caller Information</SectionTitle>
            {[
              { label: 'User ID', value: 'EMP-1042', mono: true },
              { label: 'Role', value: 'Finance Manager' },
              { label: 'Organization', value: 'Demo Organization' },
              { label: 'Duration', value: '02:43', mono: true },
              { label: 'Channel', value: 'PSTN/VoIP' },
            ].map(r => (
              <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ fontSize: 12, color: '#3a4e78' }}>{r.label}</span>
                <span style={{
                  fontSize: 12, fontWeight: 500, color: '#d5dffa',
                  fontFamily: r.mono ? "'JetBrains Mono', monospace" : undefined,
                }}>{r.value}</span>
              </div>
            ))}
          </Card>

          {/* Risk Gauge */}
          <Card style={{ padding: '20px 16px', textAlign: 'center' }}>
            <SectionTitle>Unified Risk Score</SectionTitle>
            <RiskGauge score={92} />
          </Card>
        </div>

        {/* Right: agents + decision */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Agent cards */}
          <Card style={{ padding: '16px 18px' }}>
            <SectionTitle>Security Agent Analysis</SectionTitle>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <AgentCard
                title="Voice Identity Agent"
                metrics={[{ label: 'Match Score', value: '92%', color: '#f03838' }]}
                status="SUSPICIOUS"
              />
              <AgentCard
                title="Voice Deepfake Agent"
                metrics={[{ label: 'Synthetic Prob.', value: '87%', color: '#f03838' }]}
                status="SUSPICIOUS"
              />
              <AgentCard
                title="Context / Fraud Agent"
                metrics={[{ label: 'Risk Level', value: 'HIGH', color: '#f07228' }]}
                status="SUSPICIOUS"
              />
              <AgentCard
                title="Behavior / Anomaly Agent"
                metrics={[{ label: 'Anomaly Score', value: '74%', color: '#f07228' }]}
                status="UNUSUAL"
              />
              <AgentCard
                title="Adversarial Agent"
                metrics={[{ label: 'Cross-check', value: 'FLAGGED', color: '#f03838' }]}
                status="FLAGGED"
              />
              <AgentCard
                title="Risk Fusion Engine"
                metrics={[{ label: 'Unified Score', value: '92 / 100', color: '#f03838' }]}
                status="FLAGGED"
              />
            </div>
          </Card>

          {/* Evidence Fusion */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <Card style={{ padding: '16px 18px' }}>
              <SectionTitle>Evidence Fusion</SectionTitle>
              <EvidenceRow label="Voice Identity" value="92%" color="#f03838" />
              <EvidenceRow label="Voice Deepfake" value="87%" color="#f03838" />
              <EvidenceRow label="Context / Fraud" value="HIGH" color="#f07228" />
              <EvidenceRow label="Behavior" value="74%" color="#f07228" />
              <EvidenceRow label="Adversarial" value="FLAGGED" color="#f03838" />
              <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #18234a' }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>Unified Risk Engine</div>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 700, color: '#f03838' }}>92 / 100</div>
              </div>
            </Card>

            {/* Security Decision */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <Card style={{ padding: '16px 18px', borderColor: '#f0383840' }}>
                <SectionTitle>Security Decision</SectionTitle>
                <div style={{
                  padding: '12px', borderRadius: 8,
                  background: '#2a080808', border: '1px solid #f0383850',
                  marginBottom: 12, textAlign: 'center',
                }}>
                  <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 24, fontWeight: 700, color: '#f03838', letterSpacing: '0.06em' }}>
                    BLOCK
                  </div>
                </div>
                <div style={{ fontSize: 12, color: '#6280b8', marginBottom: 8 }}>
                  Possible AI-generated voice combined with suspicious high-risk interaction context.
                </div>
                <div style={{ fontSize: 11, color: '#3a4e78' }}>
                  Policy: <span style={{ color: '#f03838', fontFamily: "'JetBrains Mono', monospace" }}>CRITICAL_RISK_BLOCK</span>
                </div>
              </Card>

              {/* MCP Panel */}
              <Card style={{ padding: '16px 18px' }}>
                <SectionTitle>Unified Security MCP</SectionTitle>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                  <span style={{ fontSize: 12, color: '#3a4e78' }}>MCP Server</span>
                  <span style={{ fontSize: 11, fontWeight: 600, color: '#4080f8', background: '#0a1838', border: '1px solid #4080f840', padding: '1px 7px', borderRadius: 4 }}>CONNECTED</span>
                </div>
                <div style={{ fontSize: 11, color: '#3a4e78', marginBottom: 8, letterSpacing: '0.06em' }}>AUTHORIZED TOOLS</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginBottom: 12 }}>
                  {['Voice Model', 'User Profile Service', 'Risk Engine', 'Security Policy', 'Audit Service'].map(t => (
                    <McpTool key={t} name={t} />
                  ))}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 8, borderTop: '1px solid #0e1838' }}>
                  <span style={{ fontSize: 11, color: '#3a4e78' }}>Unauthorized Tools</span>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#20d870' }}>0</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
                  <span style={{ fontSize: 11, color: '#3a4e78' }}>Last Auth</span>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6280b8' }}>10:42:17</span>
                </div>
              </Card>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
