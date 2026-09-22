import type { NavigateFn } from '../App';
import { PageHeader, Card } from '../components/ui';

interface PolicyRule {
  id: string;
  name: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  conditions: { field: string; op: string; value: string }[];
  actions: string[];
  enabled: boolean;
}

const policies: PolicyRule[] = [
  {
    id: 'POL-001', name: 'Critical Risk Policy', severity: 'critical', enabled: true,
    conditions: [
      { field: 'Risk Score', op: '≥', value: '80' },
      { field: 'Deepfake Probability', op: '>', value: '70%' },
    ],
    actions: ['Block Call', 'Create Critical Alert', 'Record Blockchain Audit', 'Notify Security Team'],
  },
  {
    id: 'POL-002', name: 'High Risk Policy', severity: 'high', enabled: true,
    conditions: [
      { field: 'Risk Score', op: 'between', value: '60 – 79' },
    ],
    actions: ['Require MFA Verification', 'Request Callback Confirmation', 'Create Security Alert', 'Increase Monitoring'],
  },
  {
    id: 'POL-003', name: 'Medium Risk Policy', severity: 'medium', enabled: true,
    conditions: [
      { field: 'Risk Score', op: 'between', value: '30 – 59' },
    ],
    actions: ['Flag for Review', 'Enhanced Monitoring', 'Log Event', 'Request Additional Context'],
  },
  {
    id: 'POL-004', name: 'Low Risk Policy', severity: 'low', enabled: true,
    conditions: [
      { field: 'Risk Score', op: '<', value: '30' },
    ],
    actions: ['Allow Call', 'Continue Real-Time Monitoring', 'Log Verified Event'],
  },
  {
    id: 'POL-005', name: 'Deepfake Override Policy', severity: 'critical', enabled: true,
    conditions: [
      { field: 'Deepfake Probability', op: '>', value: '85%' },
    ],
    actions: ['Immediate Block', 'Alert SOC Team', 'Trigger Incident Response', 'Record Evidence'],
  },
  {
    id: 'POL-006', name: 'Adversarial Evasion Policy', severity: 'critical', enabled: false,
    conditions: [
      { field: 'Adversarial Score', op: '>', value: '70%' },
      { field: 'Identity Confidence', op: '<', value: '40%' },
    ],
    actions: ['Block Call', 'Isolate Session', 'Full Forensic Capture'],
  },
];

const SEVERITY_COLORS = {
  critical: { color: '#f03838', bg: '#2a0808', border: '#f0383840', label: 'CRITICAL' },
  high:     { color: '#f07228', bg: '#2a1408', border: '#f0723040', label: 'HIGH' },
  medium:   { color: '#f5a020', bg: '#2a1e06', border: '#f5a02040', label: 'MEDIUM' },
  low:      { color: '#20d870', bg: '#082010', border: '#20d87040', label: 'LOW' },
};

function ConditionChip({ field, op, value }: { field: string; op: string; value: string }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '3px 10px', borderRadius: 20, background: '#080e28',
      border: '1px solid #1a2a50', fontSize: 12, whiteSpace: 'nowrap',
    }}>
      <span style={{ color: '#90a8d8' }}>{field}</span>
      <span style={{ color: '#4060a0', fontWeight: 600 }}>{op}</span>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", color: '#a0c0f8', fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function ActionChip({ action }: { action: string }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '3px 10px', borderRadius: 4, background: '#0a1428',
      border: '1px solid #18234a', fontSize: 11, color: '#8090b0',
    }}>
      <span style={{ width: 4, height: 4, borderRadius: '50%', background: '#4080f8', flexShrink: 0, display: 'inline-block' }} />
      {action}
    </div>
  );
}

export default function SecurityPoliciesScreen({ navigate: _navigate }: { navigate: NavigateFn }) {
  return (
    <div>
      <PageHeader title="Security Policies" subtitle="Deterministic enforcement rules for the Unified Risk Engine.">
        <div style={{ fontSize: 12, color: '#3a4e78' }}>
          {policies.filter(p => p.enabled).length} active · {policies.filter(p => !p.enabled).length} disabled
        </div>
      </PageHeader>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {policies.map(policy => {
          const sc = SEVERITY_COLORS[policy.severity];
          return (
            <Card key={policy.id} style={{ padding: '18px 20px', borderLeft: `3px solid ${sc.color}`, opacity: policy.enabled ? 1 : 0.55 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
                    color: sc.color, background: sc.bg, border: `1px solid ${sc.border}`,
                    padding: '2px 8px', borderRadius: 4,
                  }}>{sc.label}</span>
                  <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: '#d5dffa' }}>{policy.name}</h3>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 10, color: '#3a4e78' }}>{policy.id}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 11, color: policy.enabled ? '#20d870' : '#3a4e78', fontWeight: 600 }}>
                    {policy.enabled ? '● ENABLED' : '○ DISABLED'}
                  </span>
                  <button style={{
                    fontSize: 11, color: '#6280b8', background: '#0e1838',
                    border: '1px solid #18234a', borderRadius: 4, padding: '3px 10px', cursor: 'pointer',
                  }}>Edit</button>
                </div>
              </div>

              {/* Conditions */}
              <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 8 }}>
                  IF conditions met:
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {policy.conditions.map((c, i) => (
                    <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                      {i > 0 && <span style={{ fontSize: 10, color: '#3a5080', fontWeight: 700 }}>AND</span>}
                      <ConditionChip field={c.field} op={c.op} value={c.value} />
                    </span>
                  ))}
                </div>
              </div>

              {/* Actions */}
              <div>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 8 }}>
                  THEN execute:
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {policy.actions.map((a, i) => <ActionChip key={i} action={a} />)}
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
