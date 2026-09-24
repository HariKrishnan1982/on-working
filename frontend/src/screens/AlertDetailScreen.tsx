import { useEffect, useState } from 'react';
import type { NavigateFn, Selection } from '../App';
import { BackButton, Card, SectionTitle, RiskGauge } from '../components/ui';
import { getDecisionAuditProof, getSession, listAlerts, type AlertItem, type DecisionAuditProof, type SessionDetail } from '../lib/api';

function CheckIcon({ color }: { color: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

const FALLBACK_EVIDENCE = [
  'Identity analysis completed — match score 8% (threshold: 60%)',
  'Synthetic speech detected — AASIST probability 87%',
  'Suspicious financial context detected — high-value transfer request',
  'Behavioral anomaly — unusual access time and request pattern',
  'Adversarial cross-check failed — pattern inconsistent with registered profile',
];

export default function AlertDetailScreen({ navigate, selection }: { navigate: NavigateFn; selection: Selection }) {
  const [alert, setAlert] = useState<AlertItem | null>(null);
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [proof, setProof] = useState<DecisionAuditProof | null>(null);

  useEffect(() => {
    let cancelled = false;
    listAlerts()
      .then(d => {
        if (cancelled) return;
        const found = d.alerts.find(a => a.id === selection.alertId || a.session === selection.sessionId)
          ?? d.alerts[0] ?? null;
        if (found) setAlert(found);
      })
      .catch(() => {});
    if (selection.sessionId) {
      getSession(selection.sessionId).then(d => { if (!cancelled) setDetail(d); }).catch(() => {});
      // Read-only chain proof from the backend — never computed locally.
      getDecisionAuditProof(selection.sessionId).then(p => { if (!cancelled) setProof(p); }).catch(() => {});
    }
    return () => { cancelled = true; };
  }, [selection.alertId, selection.sessionId]);

  const risk = detail?.risk_score ?? alert?.risk ?? 92;
  const action = detail?.action_badge ?? detail?.action ?? alert?.action ?? 'BLOCKED';
  const reasons = detail?.reasons ?? FALLBACK_EVIDENCE;
  const sessionId = detail?.id ?? alert?.session ?? selection.sessionId ?? 'CALL-1042';
  const title = alert?.title ?? detail?.detection_summary ?? 'Possible Voice Cloning Attack';
  const severity = alert?.severity ?? (risk >= 80 ? 'Critical' : risk >= 60 ? 'High' : risk >= 30 ? 'Medium' : 'Low');

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
            Security Alert — {severity}
          </div>
          <h1 style={{ margin: '0 0 6px', fontSize: 22, fontWeight: 700, color: '#d5dffa' }}>
            {title}
          </h1>
          <div style={{ fontSize: 13, color: '#6280b8' }}>
            Alert ID: <span style={{ fontFamily: "'JetBrains Mono', monospace", color: '#8090b0' }}>{alert?.id ?? 'ALT-0091'}</span>
            &nbsp;&middot;&nbsp;Session: <span style={{ fontFamily: "'JetBrains Mono', monospace", color: '#8090b0' }}>{sessionId}</span>
            &nbsp;&middot;&nbsp;<span style={{ fontFamily: "'JetBrains Mono', monospace", color: '#8090b0' }}>{alert?.time ?? detail?.recorded_at ?? ''}</span>
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card style={{ padding: '20px 16px', textAlign: 'center' }}>
            <SectionTitle>Risk Score</SectionTitle>
            <RiskGauge score={risk} />
          </Card>

          <Card style={{ padding: '16px 18px' }}>
            <SectionTitle>Decision</SectionTitle>
            <div style={{
              padding: '14px', borderRadius: 8, marginBottom: 12,
              background: '#2a080810', border: '1px solid #f0383850',
              textAlign: 'center',
            }}>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 700, color: risk >= 60 ? '#f03838' : '#20d870', letterSpacing: '0.06em' }}>{action}</div>
            </div>
            <div style={{ fontSize: 12, color: '#3a4e78', marginBottom: 6 }}>Applied Policy</div>
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#f03838', background: '#2a0808', border: '1px solid #f0383830', padding: '6px 10px', borderRadius: 6 }}>
              {detail?.fired_rules[0]?.rule_id ?? 'CRITICAL_RISK_BLOCK'}
            </div>
          </Card>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card style={{ padding: '16px 20px' }}>
            <SectionTitle>Detection Evidence</SectionTitle>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {reasons.map((item, i) => (
                <div key={i} style={{
                  display: 'flex', gap: 10, alignItems: 'flex-start',
                  padding: '8px 12px', borderRadius: 6, background: '#0a1428',
                  border: '1px solid #18234a',
                }}>
                  <div style={{ marginTop: 1, flexShrink: 0 }}>
                    <CheckIcon color={risk >= 60 ? '#f03838' : '#20d870'} />
                  </div>
                  <span style={{ fontSize: 13, color: '#8090b0', lineHeight: 1.4 }}>{item}</span>
                </div>
              ))}
            </div>
          </Card>

          <Card style={{ padding: '16px 20px' }}>
            <SectionTitle>Blockchain Audit Record</SectionTitle>
            <div style={{
              padding: '14px 16px', borderRadius: 8,
              background: !proof ? '#0a1428' : proof.chain_verified && proof.anchor_status === 'anchored' ? '#082010' : '#2a1e06',
              border: `1px solid ${!proof ? '#18234a' : proof.chain_verified && proof.anchor_status === 'anchored' ? '#20d87040' : '#f5a02040'}`,
              marginBottom: 14,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <div style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: !proof ? '#3a4e78' : proof.chain_verified && proof.anchor_status === 'anchored' ? '#20d870' : '#f5a020',
                  boxShadow: '0 0 5px #20d87070',
                }} />
                <span style={{
                  fontSize: 12, fontWeight: 600, letterSpacing: '0.06em',
                  color: !proof ? '#6280b8' : proof.chain_verified && proof.anchor_status === 'anchored' ? '#20d870' : '#f5a020',
                }}>
                  {!proof ? 'AUDIT PROOF UNAVAILABLE (OFFLINE DEMO)' : proof.anchor_status === 'anchored' && proof.chain_verified ? 'INTEGRITY VERIFIED' : `CHAIN ${proof.chain_verified ? 'VERIFIED' : 'UNVERIFIED'} · ${proof.anchor_status?.toUpperCase() ?? 'UNKNOWN'}`}
                </span>
              </div>
              <div style={{ fontSize: 11, color: '#3a4e78' }}>
                {!proof
                  ? 'Backend unreachable — showing demo values, not a ledger claim.'
                  : proof.anchor_status === 'anchored'
                    ? 'Tamper-evident record confirmed on distributed ledger'
                    : 'Anchor pending — recorded locally, not yet written to Fabric. Server value is authoritative.'}
              </div>
            </div>

            {[
              { label: 'Audit Status', value: proof ? (proof.found ? 'RECORDED' : 'PENDING') : 'DEMO (offline)', color: proof ? (proof.found ? '#20d870' : '#f5a020') : '#f5a020' },
              { label: 'Blockchain Network', value: 'Hyperledger Fabric' },
              { label: 'Evidence Hash', value: detail ? `${detail.decision_hash.slice(0, 8)}...${detail.decision_hash.slice(-4)}` : '7f91b3c4...a83c', mono: true },
              { label: 'Chain Position', value: proof?.chain_position != null ? `#${proof.chain_position}` : '— (anchor pending / local fallback)', mono: true },
              { label: 'Anchor Status', value: proof?.anchor_status ?? 'unknown (offline demo)', mono: true },
              { label: 'Rules Version', value: detail?.rules_version ?? 'rules-v0', mono: true },
              { label: 'Timestamp', value: detail?.recorded_at ?? alert?.time ?? '—', mono: true },
              { label: 'Integrity', value: proof ? (proof.chain_verified ? 'VERIFIED (server)' : 'UNVERIFIED') : 'UNKNOWN (offline)', color: proof ? (proof.chain_verified ? '#20d870' : '#f03838') : '#f5a020' },
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
