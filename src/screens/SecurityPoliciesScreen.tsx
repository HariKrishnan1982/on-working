import { useEffect, useState } from 'react';
import type { NavigateFn } from '../App';
import { PageHeader, Card } from '../components/ui';
import { listPolicies, type PolicyItem } from '../lib/api';

const FALLBACK_POLICIES: PolicyItem[] = [
  {
    id: 'POL-001', name: 'Critical Risk Policy', severity: 'critical', enabled: true,
    conditions: [
      { field: 'Risk Score', op: '≥', value: '80' },
      { field: 'Deepfake Probability', op: '>', value: '70%' },
    ],
    actions: ['Block Call', 'Create Critical Alert', 'Record Blockchain Audit', 'Notify Security Team'],
    risk_level: 'CRITICAL', action: 'BLOCK',
  },
  {
    id: 'POL-002', name: 'High Risk Policy', severity: 'high', enabled: true,
    conditions: [{ field: 'Risk Score', op: 'between', value: '60 – 79' }],
    actions: ['Require MFA Verification', 'Request Callback Confirmation', 'Create Security Alert', 'Increase Monitoring'],
    risk_level: 'HIGH', action: 'ESCALATE',
  },
  {
    id: 'POL-003', name: 'Medium Risk Policy', severity: 'medium', enabled: true,
    conditions: [{ field: 'Risk Score', op: 'between', value: '30 – 59' }],
    actions: ['Flag for Review', 'Enhanced Monitoring', 'Log Event', 'Request Additional Context'],
    risk_level: 'MEDIUM', action: 'FLAG',
  },
  {
    id: 'POL-004', name: 'Low Risk Policy', severity: 'low', enabled: true,
    conditions: [{ field: 'Risk Score', op: '<', value: '30' }],
    actions: ['Allow Call', 'Continue Real-Time Monitoring', 'Log Verified Event'],
    risk_level: 'LOW', action: 'ALLOW',
  },
];

const SEVERITY_COLORS: Record<string, { color: string; bg: string; border: string; label: string }> = {
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
  const [policies, setPolicies] = useState<PolicyItem[]>(FALLBACK_POLICIES);
  const [version, setVersion] = useState<string>('offline demo');
  const [live, setLive] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listPolicies()
      .then(d => {
        if (cancelled) return;
        if (d.policies.length > 0) setPolicies(d.policies);
        setVersion(d.version ?? 'unknown');
        setLive(true);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  return (
    <div>
      <PageHeader title="Security Policies" subtitle={`Deterministic enforcement rules for the Unified Risk Engine · ${version}`}>
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
          color: live ? '#20d870' : '#f5a020',
          background: live ? '#082010' : '#2a1e06',
          border: `1px solid ${live ? '#20d87050' : '#f5a02050'}`,
          padding: '2px 8px', borderRadius: 4,
        }}>
          {live ? `● LIVE · ${version}` : '○ DEMO DATA'}
        </span>
        <div style={{ fontSize: 12, color: '#3a4e78' }}>
          {policies.filter(p => p.enabled).length} active · {policies.filter(p => !p.enabled).length} disabled
        </div>
      </PageHeader>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {policies.map(policy => {
          const sc = SEVERITY_COLORS[policy.severity] ?? SEVERITY_COLORS.medium;
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
                  <span
                    title="Demo only: rules deploy via rules.yaml, no toggle endpoint exists"
                    style={{ fontSize: 11, color: policy.enabled ? '#20d870' : '#3a4e78', fontWeight: 600 }}
                  >
                    {policy.enabled ? '● ENABLED' : '○ DISABLED'}
                  </span>
                  <button
                    disabled
                    title="Demo only: no rule-edit endpoint exists"
                    style={{
                      fontSize: 11, color: '#3a4e78', background: 'transparent',
                      border: '1px dashed #28384a', borderRadius: 4, padding: '3px 10px', cursor: 'not-allowed',
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
                  THEN execute ({policy.risk_level} → {policy.action}):
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {policy.actions.map((a, i) => <ActionChip key={i} action={a} />)}
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginTop: 16,
        padding: '10px 14px', borderRadius: 8, background: '#0a1428', border: '1px solid #18234a',
      }}>
        <span style={{
          fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
          color: '#f5a020', background: '#2a1e06', border: '1px solid #f5a02050',
          padding: '2px 7px', borderRadius: 4, whiteSpace: 'nowrap',
        }}>
          DEMO — NON-FUNCTIONAL MOCKUP
        </span>
        <span style={{ fontSize: 11, color: '#6280b8' }}>
          Rule cards are live reads of risk_engine/rules.yaml. Toggles and Edit buttons are demo-only — no rule-write endpoint exists.
        </span>
      </div>
    </div>
  );
}
