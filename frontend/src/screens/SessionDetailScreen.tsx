import { useCallback, useEffect, useState } from 'react';
import type { NavigateFn, Selection } from '../App';
import { BackButton, RiskGauge, Card, SectionTitle } from '../components/ui';
import {
  getDecisionAuditProof,
  getSession,
  type DecisionAuditProof,
  type SessionDetail,
} from '../lib/api';

// Exact privacy wording used by demo.py — the transcript is rendered here
// only and never committed to the ledger (only its SHA-256 hash is anchored).
const PRIVACY_BANNER =
  '[PRIVACY GUARD: Rendered locally in terminal only; never committed to ledger/blockchain]';

function statusLabel(status: string | undefined): string {
  switch (status) {
    case 'ok': return 'OK';
    case 'failed': return 'FAILED';
    case 'insufficient_audio': return 'INSUFFICIENT AUDIO';
    case 'not_enrolled': return 'NOT ENROLLED';
    case 'degraded': return 'DEGRADED';
    default: return (status ?? 'unknown').toUpperCase();
  }
}

function statusColor(status: string | undefined): string {
  return status === 'ok' ? '#20d870' : '#f07228';
}

function AgentCard({
  title, metrics, status,
}: {
  title: string;
  metrics: { label: string; value: string; color?: string }[];
  status: 'VERIFIED' | 'SUSPICIOUS' | 'UNUSUAL' | 'FLAGGED' | 'DEGRADED';
}) {
  const statusColors: Record<string, { color: string; bg: string }> = {
    VERIFIED:   { color: '#20d870', bg: '#082010' },
    SUSPICIOUS: { color: '#f07228', bg: '#2a1408' },
    UNUSUAL:    { color: '#f5a020', bg: '#2a1e06' },
    FLAGGED:    { color: '#f03838', bg: '#2a0808' },
    DEGRADED:   { color: '#f5a020', bg: '#2a1e06' },
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

function shortHash(h: string | null | undefined): string {
  if (!h) return '—';
  return h.length > 20 ? `${h.slice(0, 16)}…` : h;
}

export default function SessionDetailScreen({ navigate, selection }: { navigate: NavigateFn; selection: Selection }) {
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [proof, setProof] = useState<DecisionAuditProof | null>(null);
  const sessionId = selection.sessionId;

  const loadProof = useCallback(async (id: string) => {
    try {
      setProof(await getDecisionAuditProof(id));
    } catch {
      setProof(null);
    }
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    setLoading(true);
    getSession(sessionId)
      .then(d => {
        if (cancelled) return;
        setDetail(d);
        setLive(true);
        setLoading(false);
        void loadProof(d.id);
      })
      .catch(() => {
        if (cancelled) return;
        setLive(false);
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [sessionId, loadProof]);

  const spoof = detail?.evidence.spoof;
  const speaker = detail?.evidence.speaker;
  const intent = detail?.evidence.intent;
  const vad = detail?.vad ?? null;

  // No fabricated fallbacks: without a backend decision there is nothing to
  // render — the honest unavailable state below replaces the old demo values.
  if (!loading && !detail) {
    return (
      <div>
        <BackButton onClick={() => navigate('live-calls')} label="Back to Live Calls" />
        <div style={{ padding: '32px', textAlign: 'center', color: '#f03838', fontSize: 13 }}>
          Analysis unavailable — session {sessionId ? `'${sessionId}' was not found` : 'not selected'} or the
          real-time gateway is unreachable. No demo data is shown.
        </div>
      </div>
    );
  }

  const risk = detail?.risk_score ?? 0;
  const identity = detail && speaker ? Math.round(speaker.similarity_score * 100) : 0;
  const deepfake = detail && spoof ? Math.round(spoof.spoof_score * 100) : 0;
  const context = detail && intent ? Math.round(intent.scam_score * 100) : 0;
  const action = detail?.action_badge ?? detail?.action ?? '—';
  const caller = detail?.caller_id ?? '—';
  const rulesVersion = detail?.rules_version ?? '—';
  const decisionHash = detail?.decision_hash ?? '—';
  const reasons = detail?.reasons ?? [];
  const fired = detail?.fired_rules ?? [];

  const speakerVerdict = !detail
    ? 'DEGRADED'
    : speaker?.status === 'not_enrolled' || speaker?.status !== 'ok'
      ? 'DEGRADED'
      : speaker.is_match ? 'VERIFIED' : 'SUSPICIOUS';
  const spoofVerdict = !detail ? 'DEGRADED' : spoof?.status !== 'ok' ? 'DEGRADED' : spoof.is_spoofed ? 'SUSPICIOUS' : 'VERIFIED';
  const intentVerdict = !detail
    ? 'DEGRADED'
    : intent?.status !== 'ok'
      ? 'DEGRADED'
      : context >= 80 ? 'FLAGGED' : context >= 50 ? 'SUSPICIOUS' : context >= 30 ? 'UNUSUAL' : 'VERIFIED';

  return (
    <div>
      <BackButton onClick={() => navigate('live-calls')} label="Back to Live Calls" />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 20, fontWeight: 700, color: '#d5dffa' }}>
              CALL SESSION #{sessionId ?? '—'}
            </span>
            <span style={{
              fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
              color: live ? '#20d870' : '#f5a020', background: live ? '#082010' : '#2a1e06',
              border: `1px solid ${live ? '#20d87050' : '#f5a02050'}`,
              padding: '3px 8px', borderRadius: 4,
            }}>
              {loading ? '○ LOADING…' : live ? '● LIVE ANALYSIS' : '○ ANALYSIS UNAVAILABLE'}
            </span>
          </div>
          <div style={{ fontSize: 13, color: '#6280b8' }}>
            {detail?.detection_summary ?? 'Loading session analysis…'}
          </div>
          {detail && (
            <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3a4e78', marginTop: 6 }}>
              decision_hash: {decisionHash.slice(0, 24)}… · rules: {rulesVersion}
            </div>
          )}
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card style={{ padding: '16px 18px' }}>
            <SectionTitle>Caller Information</SectionTitle>
            {[
              { label: 'User ID', value: caller, mono: true },
              { label: 'Claimed Identity', value: detail?.claimed_identity ?? '—', mono: true },
              { label: 'Duration', value: detail?.duration_s != null ? `${Math.floor(detail.duration_s / 60)}:${String(Math.floor(detail.duration_s % 60)).padStart(2, '0')}` : '—', mono: true },
              { label: 'Sample Rate', value: detail?.sample_rate ? `${detail.sample_rate} Hz` : '—', mono: true },
              { label: 'Channels', value: detail?.channels != null ? String(detail.channels) : '—', mono: true },
              { label: 'Recorded', value: detail ? new Date(detail.recorded_at).toLocaleString() : '—', mono: true },
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

          <Card style={{ padding: '20px 16px', textAlign: 'center' }}>
            <SectionTitle>Unified Risk Score</SectionTitle>
            <RiskGauge score={risk} />
          </Card>

          <Card style={{ padding: '16px 18px' }}>
            <SectionTitle>Signal & VAD (Phase 1)</SectionTitle>
            <EvidenceRow
              label="Validity"
              value={!detail ? 'LOADING…' : !vad ? '—' : vad.is_valid ? 'SPEECH DETECTED' : 'INSUFFICIENT / SILENT'}
              color={!detail || !vad ? undefined : vad.is_valid ? '#20d870' : '#f07228'}
            />
            <EvidenceRow label="Voiced segments" value={vad ? String(vad.segment_count) : '—'} />
            <EvidenceRow
              label="Voiced / total"
              value={vad ? `${vad.speech_duration_s.toFixed(2)}s / ${vad.total_duration_s.toFixed(2)}s` : '—'}
            />
            <EvidenceRow label="SNR estimate" value={vad?.snr_db != null ? `${vad.snr_db.toFixed(1)} dB` : '—'} />
            <EvidenceRow label="Anti-spoof branch" value={statusLabel(spoof?.status)} color={statusColor(spoof?.status)} />
            <EvidenceRow label="Speaker branch" value={statusLabel(speaker?.status)} color={statusColor(speaker?.status)} />
            <EvidenceRow label="Intent branch" value={statusLabel(intent?.status)} color={statusColor(intent?.status)} />
            <div style={{ fontSize: 11, color: '#3a4e78', marginTop: 8 }}>
              Silence / too-short audio fails closed to FLAG via INSUFFICIENT_AUDIO.
            </div>
          </Card>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card style={{ padding: '16px 18px' }}>
            <SectionTitle>Security Agent Analysis</SectionTitle>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <AgentCard
                title="Voice Identity Agent (ECAPA-TDNN)"
                metrics={[
                  { label: 'Match Score', value: `${identity}%`, color: identity < 65 ? '#f03838' : '#20d870' },
                  { label: 'Raw cosine', value: speaker?.raw_cosine != null ? speaker.raw_cosine.toFixed(4) : '—' },
                  { label: 'Threshold', value: speaker ? speaker.threshold_used.toFixed(2) : '0.65' },
                  { label: 'Verdict', value: speaker ? (speaker.is_match ? 'MATCH' : speaker.status === 'not_enrolled' ? 'NOT ENROLLED' : 'MISMATCH') : '—', color: '#f03838' },
                ]}
                status={speakerVerdict}
              />
              <AgentCard
                title="Voice Deepfake Agent (AASIST)"
                metrics={[
                  { label: 'Synthetic Prob.', value: `${deepfake}%`, color: deepfake >= 50 ? '#f03838' : '#20d870' },
                  { label: 'Confidence', value: spoof ? `${Math.round(spoof.confidence * 100)}%` : '—' },
                  { label: 'Verdict', value: spoof ? (spoof.is_spoofed ? 'SPOOFED' : 'BONA-FIDE') : '—', color: deepfake >= 50 ? '#f03838' : '#20d870' },
                ]}
                status={spoofVerdict}
              />
              <AgentCard
                title="Context / Fraud Agent (Whisper + rules)"
                metrics={[
                  { label: 'Scam Score', value: `${context}%`, color: context >= 50 ? '#f07228' : '#20d870' },
                  { label: 'Category', value: intent ? intent.intent_category : '—' },
                  { label: 'Language', value: intent ? intent.language_detected : 'EN' },
                ]}
                status={intentVerdict}
              />
              <AgentCard
                title="Risk Fusion Engine"
                metrics={[{ label: 'Unified Score', value: `${risk} / 100`, color: risk >= 60 ? '#f03838' : '#20d870' }]}
                status={risk >= 60 ? 'FLAGGED' : 'VERIFIED'}
              />
            </div>
            <div style={{ display: 'flex', gap: 16, marginTop: 10, flexWrap: 'wrap' }}>
              {[
                { label: 'AASIST', value: spoof?.model_version ?? '—' },
                { label: 'ECAPA', value: speaker?.model_version ?? '—' },
                { label: 'ASR/Intent', value: intent?.model_version ?? '—' },
              ].map(m => (
                <span key={m.label} style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3a4e78' }}>
                  {m.label}: <span style={{ color: '#6280b8' }}>{m.value}</span>
                </span>
              ))}
            </div>
          </Card>

          <Card style={{ padding: '16px 18px' }}>
            <SectionTitle>Transcript & Scam Intent (Phase 4)</SectionTitle>
            <div style={{
              padding: '8px 12px', borderRadius: 6, marginBottom: 12,
              background: '#2a1e06', border: '1px solid #f5a02040',
              fontSize: 11, color: '#f5a020', fontWeight: 600,
            }}>
              {PRIVACY_BANNER}
            </div>
            <div style={{
              padding: '12px 14px', borderRadius: 8, marginBottom: 12,
              background: '#080c24', border: '1px solid #18234a',
              fontSize: 13, color: '#a0b8e0', fontStyle: 'italic', lineHeight: 1.5,
            }}>
              {intent?.transcript ? `"${intent.transcript}"` : '(no speech transcribed)'}
            </div>
            <EvidenceRow label="Scam-intent score" value={intent ? `${intent.scam_score.toFixed(3)} / 1.0` : '—'} color={context >= 50 ? '#f07228' : '#20d870'} />
            <EvidenceRow label="Indicators" value={intent && intent.scam_indicators.length > 0 ? intent.scam_indicators.join(', ') : 'none (clean intent)'} />
            <EvidenceRow label="Transcript SHA-256" value={shortHash(intent?.transcript_hash_sha256)} />
            <div style={{ fontSize: 11, color: '#3a4e78', marginTop: 8 }}>
              Only the transcript hash is anchored on-chain — never the text.
            </div>
          </Card>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <Card style={{ padding: '16px 18px' }}>
              <SectionTitle>Evidence Fusion & Risk Rules</SectionTitle>
              <EvidenceRow label="Voice Identity" value={`${identity}%`} color={identity < 65 ? '#f03838' : '#20d870'} />
              <EvidenceRow label="Voice Deepfake" value={`${deepfake}%`} color={deepfake >= 50 ? '#f03838' : '#20d870'} />
              <EvidenceRow label="Context / Fraud" value={`${context}%`} color={context >= 50 ? '#f07228' : '#20d870'} />
              <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid #18234a' }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>Unified Risk Engine</div>
                <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 700, color: risk >= 60 ? '#f03838' : '#20d870' }}>{risk} / 100</div>
              </div>
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>
                  Fired Rules ({fired.length})
                </div>
                {fired.length === 0 && (
                  <div style={{ fontSize: 12, color: '#20d870' }}>None — all signals within clean bounds.</div>
                )}
                {fired.map(r => (
                  <div key={r.rule_id} style={{ marginBottom: 10, padding: '8px 10px', background: '#0a1428', border: '1px solid #18234a', borderRadius: 6 }}>
                    <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, fontWeight: 700, color: '#f03838', marginBottom: 2 }}>
                      {r.rule_id} · {r.risk_level} → {r.action}
                    </div>
                    <div style={{ fontSize: 12, color: '#8090b0', marginBottom: 2 }}>{r.description}</div>
                    <div style={{ fontSize: 11, color: '#3a4e78' }}>{r.condition_summary}</div>
                  </div>
                ))}
              </div>
            </Card>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <Card style={{ padding: '16px 18px', borderColor: '#f0383840' }}>
                <SectionTitle>Security Decision</SectionTitle>
                <div style={{
                  padding: '12px', borderRadius: 8,
                  background: '#2a080808', border: '1px solid #f0383850',
                  marginBottom: 12, textAlign: 'center',
                }}>
                  <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 24, fontWeight: 700, color: risk >= 60 ? '#f03838' : '#20d870', letterSpacing: '0.06em' }}>
                    {action}
                  </div>
                </div>
                {reasons.map((r, i) => (
                  <div key={i} style={{ fontSize: 12, color: '#6280b8', marginBottom: 8 }}>{r}</div>
                ))}
                <div style={{ fontSize: 11, color: '#3a4e78' }}>
                  Policy: <span style={{ color: '#f03838', fontFamily: "'JetBrains Mono', monospace" }}>{fired[0]?.rule_id ?? 'RISK_ENGINE'}</span>
                </div>
              </Card>

              <Card style={{ padding: '16px 18px' }}>
                <SectionTitle>Audit Proof</SectionTitle>
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 10, color: '#3a4e78', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 4 }}>Decision SHA-256</div>
                  <div style={{
                    fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
                    color: '#6280b8', background: '#080e28', border: '1px solid #18234a',
                    padding: '6px 10px', borderRadius: 6, wordBreak: 'break-all',
                  }}>{decisionHash}</div>
                </div>
                <EvidenceRow label="Chain record" value={proof && proof.found ? shortHash(proof.record_hash) : '— (not on chain yet)'} />
                <EvidenceRow label="Chain position" value={proof?.chain_position != null ? `#${proof.chain_position}` : '—'} />
                <EvidenceRow
                  label="Anchor status"
                  value={proof?.anchor_status ?? '—'}
                  color={proof?.anchor_status === 'anchored' ? '#20d870' : '#f5a020'}
                />
                <EvidenceRow label="Outbox" value={proof?.outbox_status ?? '—'} />
                <EvidenceRow
                  label="Chain verified"
                  value={proof ? (proof.chain_verified ? 'YES' : 'NO') : '—'}
                  color={proof ? (proof.chain_verified ? '#20d870' : '#f03838') : undefined}
                />
                <EvidenceRow label="Ledger source" value={proof?.source ?? '—'} />
                {proof?.note && (
                  <div style={{ fontSize: 11, color: '#3a4e78', marginTop: 8 }}>{proof.note}</div>
                )}
                {sessionId && live && (
                  <button
                    onClick={() => void loadProof(sessionId)}
                    style={{ marginTop: 10, padding: '6px 12px', background: '#0e1838', border: '1px solid #18234a', borderRadius: 5, color: '#6280b8', fontSize: 12, cursor: 'pointer' }}
                  >
                    Refresh audit proof
                  </button>
                )}
              </Card>
            </div>
          </div>

          <Card style={{ padding: '12px 18px' }}>
            <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
              {[
                { label: 'AASIST', ms: spoof?.processing_time_ms },
                { label: 'ECAPA', ms: speaker?.processing_time_ms },
                { label: 'Whisper/Intent', ms: intent?.processing_time_ms },
              ].map(t => (
                <span key={t.label} style={{ fontSize: 11, color: '#3a4e78' }}>
                  {t.label}: <span style={{ fontFamily: "'JetBrains Mono', monospace", color: '#6280b8' }}>{t.ms != null ? `${t.ms.toFixed(1)} ms` : '—'}</span>
                </span>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
