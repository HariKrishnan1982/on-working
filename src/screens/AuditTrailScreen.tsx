import { useState } from 'react';
import type { NavigateFn } from '../App';
import { PageHeader, RiskBadge, ActionBadge, Card, SectionTitle } from '../components/ui';

const auditRecords = [
  { id: 'AUD-0182', time: '10:42:18', session: 'CALL-1042', event: 'Voice Clone', risk: 92, action: 'BLOCK', hash: '7f91b3c4...a83c', verified: true },
  { id: 'AUD-0181', time: '10:39:11', session: 'CALL-1038', event: 'Fraud Risk', risk: 68, action: 'MFA', hash: 'a30d14f9...e21b', verified: true },
  { id: 'AUD-0180', time: '10:34:55', session: 'CALL-1035', event: 'Behavior Anomaly', risk: 63, action: 'MFA', hash: 'b52c98d1...f40e', verified: true },
  { id: 'AUD-0179', time: '10:31:42', session: 'CALL-1031', event: 'Verified Call', risk: 24, action: 'ALLOW', hash: 'c18a7f3e...d09a', verified: true },
  { id: 'AUD-0178', time: '10:28:30', session: 'CALL-1028', event: 'Identity Mismatch', risk: 52, action: 'MFA', hash: 'f83b20c7...7e1d', verified: true },
  { id: 'AUD-0177', time: '10:22:41', session: 'CALL-1025', event: 'Adversarial Input', risk: 81, action: 'BLOCK', hash: 'd47c99e2...b15f', verified: true },
  { id: 'AUD-0176', time: '10:15:08', session: 'CALL-1022', event: 'Verified Call', risk: 19, action: 'ALLOW', hash: 'e90f11a4...c83d', verified: true },
  { id: 'AUD-0175', time: '10:08:22', session: 'CALL-1018', event: 'Context Fraud', risk: 67, action: 'MFA', hash: '1f28b5d3...a70c', verified: true },
];

export default function AuditTrailScreen({ navigate: _navigate }: { navigate: NavigateFn }) {
  const [selected, setSelected] = useState<typeof auditRecords[0] | null>(auditRecords[0]);

  return (
    <div>
      <PageHeader
        title="Tamper-Evident Audit Trail"
        subtitle="Security decisions recorded on Hyperledger Fabric blockchain for verification and compliance."
      />

      {/* Blockchain banner */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 16px', borderRadius: 8, marginBottom: 20,
        background: '#080e28', border: '1px solid #4080f830',
      }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#4080f8', boxShadow: '0 0 6px #4080f870' }} />
        <span style={{ fontSize: 12, color: '#4080f8', fontWeight: 600 }}>HYPERLEDGER FABRIC</span>
        <span style={{ fontSize: 12, color: '#3a4e78' }}>·</span>
        <span style={{ fontSize: 12, color: '#6280b8' }}>Channel: voiceshield-audit</span>
        <span style={{ fontSize: 12, color: '#3a4e78' }}>·</span>
        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#6280b8' }}>4,291,847 blocks</span>
        <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 600, color: '#20d870' }}>● CONNECTED</span>
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
          {auditRecords.map((rec, i) => (
            <div
              key={rec.id}
              onClick={() => setSelected(rec)}
              style={{
                display: 'grid', gridTemplateColumns: '90px 80px 1fr 60px 80px 100px',
                padding: '11px 16px', cursor: 'pointer', transition: 'background 0.12s',
                borderBottom: i < auditRecords.length - 1 ? '1px solid #0e1838' : 'none',
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
              <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, fontWeight: 600, color: '#20d870' }}>
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#20d870" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                Verified
              </span>
            </div>
          ))}
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
              { label: 'Timestamp', value: `2026-09-20 ${selected.time}`, mono: true },
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
              background: '#082010', border: '1px solid #20d87040',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#20d870" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#20d870', letterSpacing: '0.06em' }}>INTEGRITY VERIFIED</div>
                <div style={{ fontSize: 10, color: '#3a6030', marginTop: 1 }}>Block signature valid · Immutable record</div>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
