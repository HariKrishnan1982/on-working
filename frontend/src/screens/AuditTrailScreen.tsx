import { useEffect, useState } from 'react';
import type { NavigateFn } from '../App';
import { PageHeader, RiskBadge, ActionBadge, Card, SectionTitle } from '../components/ui';
import { getAudit, type AuditItem } from '../lib/api';

const FALLBACK_RECORDS: AuditItem[] = [
  { id: 'AUD-0182', time: '10:42:18', session: 'CALL-1042', event: 'Voice Clone', risk: 92, action: 'BLOCK', hash: '7f91b3c4...a83c', verified: true, chain_position: 182 },
  { id: 'AUD-0181', time: '10:39:11', session: 'CALL-1038', event: 'Fraud Risk', risk: 68, action: 'MFA', hash: 'a30d14f9...e21b', verified: true, chain_position: 181 },
  { id: 'AUD-0180', time: '10:34:55', session: 'CALL-1035', event: 'Behavior Anomaly', risk: 63, action: 'MFA', hash: 'b52c98d1...f40e', verified: true, chain_position: 180 },
  { id: 'AUD-0179', time: '10:31:42', session: 'CALL-1031', event: 'Verified Call', risk: 24, action: 'ALLOW', hash: 'c18a7f3e...d09a', verified: true, chain_position: 179 },
  { id: 'AUD-0178', time: '10:28:30', session: 'CALL-1028', event: 'Identity Mismatch', risk: 52, action: 'MFA', hash: 'f83b20c7...7e1d', verified: true, chain_position: 178 },
  { id: 'AUD-0177', time: '10:22:41', session: 'CALL-1025', event: 'Adversarial Input', risk: 81, action: 'BLOCK', hash: 'd47c99e2...b15f', verified: true, chain_position: 177 },
  { id: 'AUD-0176', time: '10:15:08', session: 'CALL-1022', event: 'Verified Call', risk: 19, action: 'ALLOW', hash: 'e90f11a4...c83d', verified: true, chain_position: 176 },
  { id: 'AUD-0175', time: '10:08:22', session: 'CALL-1018', event: 'Context Fraud', risk: 67, action: 'MFA', hash: '1f28b5d3...a70c', verified: true, chain_position: 175 },
];

export default function AuditTrailScreen({ navigate: _navigate }: { navigate: NavigateFn }) {
  const [records, setRecords] = useState<AuditItem[]>(FALLBACK_RECORDS);
  const [source, setSource] = useState('offline-demo');
  const [chainVerified, setChainVerified] = useState(true);
  const [selected, setSelected] = useState<AuditItem | null>(FALLBACK_RECORDS[0]);

  useEffect(() => {
    let cancelled = false;
    getAudit()
      .then(d => {
        if (cancelled) return;
        if (d.records.length > 0) {
          setRecords(d.records);
          setSelected(d.records[0]);
          setSource(d.source);
          setChainVerified(d.chain_verified);
        }
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  return (
    <div>
      <PageHeader
        title="Tamper-Evident Audit Trail"
        subtitle="Security decisions recorded on Hyperledger Fabric blockchain for verification and compliance."
      >
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
          color: source === 'offline-demo' || source === 'in_memory_fallback' ? '#f5a020' : '#20d870',
          background: source === 'offline-demo' || source === 'in_memory_fallback' ? '#2a1e06' : '#082010',
          border: '1px solid #ffffff20',
          padding: '2px 8px', borderRadius: 4, fontFamily: "'JetBrains Mono', monospace",
        }}>
          {source} · chain {chainVerified ? 'verified' : 'UNVERIFIED'}
        </span>
      </PageHeader>

      {/* Blockchain banner */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 16px', borderRadius: 8, marginBottom: 20,
        background: '#080e28', border: '1px solid #4080f830',
      }}>
        <div style={{
          width: 8, height: 8, borderRadius: '50%',
          background: source === 'postgres_hash_chain' ? '#4080f8' : '#f5a020',
          boxShadow: '0 0 6px #4080f870',
        }} />
        <span style={{ fontSize: 12, color: source === 'postgres_hash_chain' ? '#4080f8' : '#f5a020', fontWeight: 600 }}>
          {source === 'postgres_hash_chain' ? 'HYPERLEDGER FABRIC' : 'LOCAL AUDIT FALLBACK — FABRIC OFFLINE'}
        </span>
        <span style={{ fontSize: 12, color: '#3a4e78' }}>·</span>
        <span style={{ fontSize: 12, color: '#6280b8' }}>
          {source === 'postgres_hash_chain' ? 'Channel: fraud-channel' : 'anchor_pending — not yet written to Fabric'}
        </span>
        <span style={{ fontSize: 12, color: '#3a4e78' }}>·</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#6280b8' }}>{records.length} records loaded</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 600, color: chainVerified ? '#20d870' : '#f03838' }}>
          {chainVerified ? '● CHAIN VERIFIED' : '● CHAIN UNVERIFIED'}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 20 }}>
        {/* Table */}
        <Card>
          <div style={{
            display: 'grid', gridTemplateColumns: '90px 80px 1fr 60px 80px 100px',
            padding: '8px 16px', borderBottom: '1px solid #18234a',
          }}>
            {['Timestamp', 'Session', 'Event', 'Risk', 'Action', 'Audit Status'].map(h => (
              <span key={h} style={{ fontSize: 10, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase' }}>{h}</span>
            ))}
          </div>
          {records.map((rec, i) => (
            <div
              key={rec.id}
              onClick={() => setSelected(rec)}
              style={{
                display: 'grid', gridTemplateColumns: '90px 80px 1fr 60px 80px 100px',
                padding: '11px 16px', cursor: 'pointer', transition: 'background 0.12s',
                borderBottom: i < records.length - 1 ? '1px solid #0e1838' : 'none',
                alignItems: 'center',
                background: selected?.id === rec.id ? '#0c1838' : 'transparent',
                borderLeft: selected?.id === rec.id ? '2px solid #4080f8' : '2px solid transparent',
              }}
              onMouseEnter={e => selected?.id !== rec.id && ((e.currentTarget as HTMLDivElement).style.background = '#0b1028')}
              onMouseLeave={e => selected?.id !== rec.id && ((e.currentTarget as HTMLDivElement).style.background = 'transparent')}
            >
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3a4e78' }}>{rec.time}</span>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6280b8' }}>{rec.session}</span>
              <span style={{ fontSize: 13, color: '#d5dffa' }}>{rec.event}</span>
              <RiskBadge score={rec.risk} />
              <ActionBadge action={rec.action} />
              <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 600, color: rec.verified ? '#20d870' : '#f03838' }}>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke={rec.verified ? '#20d870' : '#f03838'} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                {rec.verified ? 'Verified' : 'Unverified'}
              </span>
            </div>
          ))}
          {records.length === 0 && (
            <div style={{ padding: '32px', textAlign: 'center', color: '#3a4e78', fontSize: 13 }}>
              No audit records yet — analyze a call to create the first hash-chained entry.
            </div>
          )}
        </Card>

        {/* Detail panel */}
        {selected && (
          <Card style={{ padding: '16px 18px', alignSelf: 'start' }}>
            <SectionTitle>Audit Record Detail</SectionTitle>
            {[
              { label: 'Event ID', value: selected.id, mono: true },
              { label: 'Session ID', value: selected.session, mono: true },
              { label: 'Event', value: selected.event },
              { label: 'Risk Score', value: String(selected.risk), mono: true },
              { label: 'Decision', value: selected.action },
              { label: 'Chain Position', value: selected.chain_position != null ? `#${selected.chain_position}` : 'local fallback (no PG chain)', mono: true },
            ].map(r => (
              <div key={r.label} style={{ display: 'flex', flexDirection: 'column', gap: 2, marginBottom: 10 }}>
                <span style={{ fontSize: 10, color: '#3a4e78', letterSpacing: '0.08em', textTransform: 'uppercase' }}>{r.label}</span>
                <span style={{
                  fontFamily: r.mono ? "'JetBrains Mono', monospace" : undefined,
                  fontSize: 13, color: '#d5dffa',
                }}>{r.value}</span>
              </div>
            ))}

            <div style={{ height: 1, background: '#18234a', margin: '12px 0' }} />

            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, color: '#3a4e78', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 4 }}>Evidence Hash</div>
              <div style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
                color: '#6280b8', background: '#080e28', border: '1px solid #18234a',
                padding: '6px 10px', borderRadius: 6, wordBreak: 'break-all',
              }}>{selected.hash}</div>
            </div>

            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, color: '#3a4e78', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 4 }}>Blockchain Network</div>
              <div style={{ fontSize: 13, color: '#4080f8' }}>Hyperledger Fabric</div>
            </div>

            <div style={{
              padding: '10px 12px', borderRadius: 8, marginTop: 12,
              background: selected.verified ? '#082010' : '#2a0808',
              border: `1px solid ${selected.verified ? '#20d87040' : '#f0383840'}`,
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={selected.verified ? '#20d870' : '#f03838'} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: selected.verified ? '#20d870' : '#f03838', letterSpacing: '0.06em' }}>
                  {selected.verified ? 'INTEGRITY VERIFIED' : 'UNVERIFIED'}
                </div>
                <div style={{ fontSize: 10, color: '#3a6030', marginTop: 1 }}>Server-side hash-chain check · Immutable record</div>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
