import type { NavigateFn } from '../App';
import { BackButton, Card, SectionTitle, RiskGauge } from '../components/ui';

function CheckIcon({ color }: { color: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

const evidenceItems = [
  'Identity analysis completed — match score 8% (threshold: 60%)',
  'Synthetic speech detected — RawNet2 probability 87%',
  'Suspicious financial context detected — high-value transfer request',
  'Behavioral anomaly — unusual access time and request pattern',
  'Adversarial cross-check failed — pattern inconsistent with registered profile',
];

export default function AlertDetailScreen({ navigate }: { navigate: NavigateFn }) {
  return (
    <div>
      <BackButton onClick={() => navigate('alerts')} label="Back to Alerts" />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <div style={{
            display: 'inline-block', fontSize: 10, fontWeight: 700,
            letterSpacing: '0.12em', color: '#f03838', background: '#2a0808',
            border: '1px solid #f0383840', padding: '3px 10px', borderRadius: 4,
            marginBottom: 10, textTransform: 'uppercase',
          }}>
            Security Alert — Critical
          </div>
          <h1 style={{ margin: '0 0 6px', fontSize: 22, fontWeight: 700, color: '#d5dffa' }}>
            Possible Voice Cloning Attack
          </h1>
          <div style={{ fontSize: 13, color: '#6280b8' }}>
            Alert ID: <span style={{ fontFamily: "'JetBrains Mono', monospace", color: '#8090b0' }}>ALT-0091</span>
            &nbsp;&middot;&nbsp;Session: <span style={{ fontFamily: "'JetBrains Mono', monospace", color: '#8090b0' }}>CALL-1042</span>
            &nbsp;&middot;&nbsp;<span style={{ fontFamily: "'JetBrains Mono', monospace", color: '#8090b0' }}>2026-09-20 10:42:17 UTC</span>
          </div>
        </div>
        <button onClick={() => navigate('audit-trail')} style={{
          padding: '8px 16px', background: '#0a1428', border: '1px solid #2040a0',
          borderRadius: 6, color: '#4080f8', fontSize: 12, fontWeight: 600, cursor: 'pointer',
        }}>
          View Audit Record →
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 20 }}>
        {/* Risk score */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card style={{ padding: '20px 16px', textAlign: 'center' }}>
            <SectionTitle>Risk Score</SectionTitle>
            <RiskGauge score={92} />
          </Card>

          <Card style={{ padding: '16px 18px' }}>
            <SectionTitle>Decision</SectionTitle>
            <div style={{
              padding: '14px', borderRadius: 8, marginBottom: 12,
              background: '#2a080810', border: '1px solid #f0383850',
              textAlign: 'center',
            }}>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 700, color: '#f03838', letterSpacing: '0.06em' }}>BLOCKED</div>
            </div>
            <div style={{ fontSize: 12, color: '#3a4e78', marginBottom: 6 }}>Applied Policy</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#f03838', background: '#2a0808', border: '1px solid #f0383830', padding: '6px 10px', borderRadius: 6 }}>
              CRITICAL_RISK_BLOCK
            </div>
          </Card>
        </div>

        {/* Right column */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Detection evidence */}
          <Card style={{ padding: '16px 20px' }}>
            <SectionTitle>Detection Evidence</SectionTitle>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {evidenceItems.map((item, i) => (
                <div key={i} style={{
                  display: 'flex', gap: 10, alignItems: 'flex-start',
                  padding: '8px 12px', borderRadius: 6, background: '#0a1428',
                  border: '1px solid #18234a',
                }}>
                  <div style={{ marginTop: 1, flexShrink: 0 }}>
                    <CheckIcon color="#f03838" />
                  </div>
                  <span style={{ fontSize: 13, color: '#8090b0', lineHeight: 1.4 }}>{item}</span>
                </div>
              ))}
            </div>
          </Card>

          {/* Blockchain audit */}
          <Card style={{ padding: '16px 20px' }}>
            <SectionTitle>Blockchain Audit Record</SectionTitle>
            <div style={{
              padding: '14px 16px', borderRadius: 8,
              background: '#080e28', border: '1px solid #4080f830',
              marginBottom: 14,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#20d870', boxShadow: '0 0 5px #20d87070' }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: '#20d870', letterSpacing: '0.06em' }}>INTEGRITY VERIFIED</span>
              </div>
              <div style={{ fontSize: 11, color: '#3a4e78' }}>Tamper-evident record confirmed on distributed ledger</div>
            </div>

            {[
              { label: 'Audit Status', value: 'RECORDED', color: '#20d870' },
              { label: 'Blockchain Network', value: 'Hyperledger Fabric' },
              { label: 'Evidence Hash', value: '7f91b3c4...a83c', mono: true },
              { label: 'Block Height', value: '#4,291,847', mono: true },
              { label: 'Timestamp', value: '2026-09-20 10:42:18 UTC', mono: true },
              { label: 'Integrity', value: 'VERIFIED', color: '#20d870' },
            ].map(r => (
              <div key={r.label} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '7px 0', borderBottom: '1px solid #0e1838',
              }}>
                <span style={{ fontSize: 12, color: '#3a4e78' }}>{r.label}</span>
                <span style={{
                  fontFamily: r.mono ? "'JetBrains Mono', monospace" : undefined,
                  fontSize: 12, fontWeight: r.color ? 600 : 400,
                  color: r.color ?? '#d5dffa',
                }}>{r.value}</span>
              </div>
            ))}
          </Card>
        </div>
      </div>
    </div>
  );
}
