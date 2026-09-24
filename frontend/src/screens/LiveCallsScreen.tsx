import { useCallback, useEffect, useRef, useState } from 'react';
import type { NavigateFn, Selection } from '../App';
import { PageHeader, RiskBadge, ActionBadge, riskColor, Card, Btn } from '../components/ui';
import {
  analyzeUpload,
  createLiveSession,
  endLiveSession,
  getLiveSession,
  getTelephonyStatus,
  listSessions,
  listTelephonyCalls,
  liveEventsUrl,
  postLiveOffer,
  type LiveEvent,
  type LiveSessionSnapshot,
  type LiveWindow,
  type SessionCall,
  type TelephonyCall,
  type TelephonyStatus,
} from '../lib/api';

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

// ─── Live-call phase (frontend mirror of the backend-owned LiveState) ───────
// The backend is authoritative; this phase only reflects confirmed states:
// IDLE → CREATING → CONNECTING → CONNECTED → RECEIVING → PROCESSING →
// ANALYSIS (final) / ENDED, with FAILED on any genuine error.
type LivePhase =
  | 'IDLE' | 'CREATING' | 'CONNECTING' | 'CONNECTED'
  | 'RECEIVING' | 'PROCESSING' | 'ANALYSIS' | 'ENDED' | 'FAILED';

const PHASE_LABEL: Record<LivePhase, string> = {
  IDLE: 'Idle',
  CREATING: 'Creating session…',
  CONNECTING: 'Connecting…',
  CONNECTED: 'Live Audio Connected',
  RECEIVING: 'Audio stream active',
  PROCESSING: 'Processing analysis window…',
  ANALYSIS: 'Analysis Window Processed',
  ENDED: 'Call ended',
  FAILED: 'Failed',
};

function micErrorMessage(e: unknown): string {
  if (e instanceof DOMException || (e as { name?: string })?.name) {
    const name = (e as { name?: string }).name || '';
    if (name === 'NotAllowedError') return 'Microphone permission denied';
    if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'Microphone missing';
    if (name === 'NotReadableError') return 'Microphone unavailable (in use by another app)';
    if (name === 'SecurityError') return 'Microphone blocked: insecure context (use HTTPS or localhost)';
  }
  if (e instanceof Error) return e.message;
  return 'Microphone unavailable';
}

export default function LiveCallsScreen({ navigate: _navigate, selection }: { navigate: NavigateFn; selection: Selection }) {
  // Past analyzed sessions (real backend rows only — never demo data).
  const [calls, setCalls] = useState<SessionCall[]>([]);
  const [gatewayReachable, setGatewayReachable] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [callerId, setCallerId] = useState('+919876543210');
  const [claimedIdentity, setClaimedIdentity] = useState('');
  const [languageHint, setLanguageHint] = useState('EN');
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Live-call state (all values confirmed by the backend, never invented).
  const [phase, setPhase] = useState<LivePhase>('IDLE');
  const [liveError, setLiveError] = useState<string | null>(null);
  const [liveSession, setLiveSession] = useState<LiveSessionSnapshot | null>(null);
  const [windows, setWindows] = useState<LiveWindow[]>([]);
  const [audioLevel, setAudioLevel] = useState(0);
  const [connectMs, setConnectMs] = useState<number | null>(null);
  const [starting, setStarting] = useState(false);

  // Telephony ingress (real backend state only — never demo calls).
  const [telephonyStatus, setTelephonyStatus] = useState<TelephonyStatus | null>(null);
  const [telephonyCalls, setTelephonyCalls] = useState<TelephonyCall[]>([]);
  const [telephonyNote, setTelephonyNote] = useState<string | null>(null);

  const fileRef = useRef<HTMLInputElement>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number>(0);
  const pollRef = useRef<number>(0);
  const offerStartRef = useRef(0);
  const sessionIdRef = useRef<string | null>(null);
  const phaseRef = useRef<LivePhase>('IDLE');
  const setPhaseBoth = (p: LivePhase) => { phaseRef.current = p; setPhase(p); };

  const refresh = useCallback(async () => {
    try {
      const data = await listSessions(200);
      // A reachable backend returning zero sessions is an honest empty
      // state — never backfilled with demo rows.
      setCalls(data.sessions);
      setGatewayReachable(true);
    } catch {
      // Gateway unavailable: show the honest banner + empty list.
      setCalls([]);
      setGatewayReachable(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [refresh]);

  const refreshTelephony = useCallback(async () => {
    try {
      const [status, calls] = await Promise.all([getTelephonyStatus(), listTelephonyCalls()]);
      setTelephonyStatus(status);
      setTelephonyCalls(calls.calls);
    } catch {
      setTelephonyStatus(null);
      setTelephonyCalls([]);
    }
  }, []);

  useEffect(() => {
    refreshTelephony();
    const id = setInterval(refreshTelephony, 15000);
    return () => clearInterval(id);
  }, [refreshTelephony]);

  const openTelephonyAnalysis = useCallback(async (call: TelephonyCall) => {
    setTelephonyNote(null);
    try {
      const live = await getLiveSession(call.live_session_id);
      if (live.result_session_id) selection.openSession(live.result_session_id);
      else setTelephonyNote(`Risk analysis not yet available for call ${call.session_id.slice(0, 8)}…`);
    } catch {
      setTelephonyNote('Risk analysis unavailable — gateway unreachable.');
    }
  }, [selection]);

  const stopLocalMedia = useCallback(() => {
    cancelAnimationFrame(rafRef.current);
    window.clearInterval(pollRef.current);
    if (audioCtxRef.current) {
      void audioCtxRef.current.close().catch(() => undefined);
      audioCtxRef.current = null;
    }
    analyserRef.current = null;
    if (streamRef.current) {
      for (const t of streamRef.current.getTracks()) t.stop();
      streamRef.current = null;
    }
    if (pcRef.current) {
      try { pcRef.current.close(); } catch { /* already closed */ }
      pcRef.current = null;
    }
    if (wsRef.current) {
      try { wsRef.current.close(); } catch { /* already closed */ }
      wsRef.current = null;
    }
    setAudioLevel(0);
  }, []);

  // Release microphone / peer connection if the user navigates away mid-call.
  useEffect(() => () => {
    const sid = sessionIdRef.current;
    if (sid && (phaseRef.current === 'CONNECTED' || phaseRef.current === 'RECEIVING' || phaseRef.current === 'PROCESSING')) {
      void endLiveSession(sid).catch(() => undefined);
    }
    cancelAnimationFrame(rafRef.current);
    window.clearInterval(pollRef.current);
    if (audioCtxRef.current) void audioCtxRef.current.close().catch(() => undefined);
    if (streamRef.current) for (const t of streamRef.current.getTracks()) t.stop();
    if (pcRef.current) try { pcRef.current.close(); } catch { /* noop */ }
    if (wsRef.current) try { wsRef.current.close(); } catch { /* noop */ }
  }, []);

  const startLevelMeter = useCallback((stream: MediaStream) => {
    const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return; // no meter without WebAudio — never fake one
    const ctx = new Ctx();
    audioCtxRef.current = ctx;
    const src = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    src.connect(analyser);
    analyserRef.current = analyser;
    const buf = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) {
        const v = (buf[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / buf.length);
      setAudioLevel(Math.min(100, Math.round(rms * 300)));
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const handleEvent = useCallback((ev: LiveEvent) => {
    switch (ev.type) {
      case 'session.connected':
        setPhaseBoth('CONNECTED');
        if (offerStartRef.current) setConnectMs(Math.round(performance.now() - offerStartRef.current));
        break;
      case 'audio.receiving':
        setPhaseBoth('RECEIVING');
        break;
      case 'analysis.started':
        setPhaseBoth('PROCESSING');
        break;
      case 'analysis.completed': {
        const d = ev.data as unknown as {
          final?: boolean; window_index?: number; audio_s?: number;
          risk_level?: string; action?: string; risk_score_100?: number;
          detection_summary?: string; started_at?: string; finished_at?: string;
          latency_ms?: number; result_session_id?: string;
        };
        if (d.final) {
          setPhaseBoth('ANALYSIS');
          void getLiveSession(ev.session_id).then(setLiveSession).catch(() => undefined);
          void refresh();
        } else if (
          typeof d.window_index === 'number' && typeof d.audio_s === 'number'
          && typeof d.risk_level === 'string' && typeof d.action === 'string'
          && typeof d.risk_score_100 === 'number' && typeof d.latency_ms === 'number'
        ) {
          const win: LiveWindow = {
            window_index: d.window_index,
            audio_s: d.audio_s,
            risk_level: d.risk_level,
            action: d.action,
            risk_score_100: d.risk_score_100,
            detection_summary: String(d.detection_summary ?? ''),
            started_at: String(d.started_at ?? ''),
            finished_at: String(d.finished_at ?? ''),
            latency_ms: d.latency_ms,
          };
          setWindows(prev => prev.some(w => w.window_index === win.window_index)
            ? prev
            : [...prev, win]);
          // Window processed — keep receiving unless the call ended.
          if (phaseRef.current === 'PROCESSING') setPhaseBoth('RECEIVING');
        }
        break;
      }
      case 'session.ended':
        if (phaseRef.current !== 'ANALYSIS') setPhaseBoth('ENDED');
        void refresh();
        break;
      case 'session.error': {
        const msg = String((ev.data as { error?: unknown }).error ?? 'Analysis unavailable');
        // A terminal error before any final result fails the call honestly.
        setLiveError(msg);
        setPhaseBoth('FAILED');
        break;
      }
      default:
        break;
    }
  }, [refresh]);

  const pollSnapshot = useCallback(async (sid: string) => {
    try {
      const snap = await getLiveSession(sid);
      setLiveSession(snap);
      setWindows(snap.windows);
      if (snap.state === 'RECEIVING_AUDIO') setPhaseBoth('RECEIVING');
      else if (snap.state === 'PROCESSING') setPhaseBoth('PROCESSING');
      else if (snap.state === 'CONNECTED') setPhaseBoth('CONNECTED');
      else if (snap.state === 'ENDED' && phaseRef.current !== 'ANALYSIS') setPhaseBoth('ENDED');
      else if (snap.state === 'FAILED') {
        setLiveError(snap.error || 'WebRTC connection failed');
        setPhaseBoth('FAILED');
      }
      if (snap.final_status === 'complete' && snap.result_session_id) setPhaseBoth('ANALYSIS');
      else if (snap.final_status === 'failed' && snap.final_error && phaseRef.current !== 'ANALYSIS') {
        setLiveError(snap.final_error);
        if (snap.state === 'ENDED') setPhaseBoth('ENDED');
      }
    } catch { /* polling is best-effort; WS is primary */ }
  }, []);

  const startLiveCall = useCallback(async () => {
    if (starting || (phase !== 'IDLE' && phase !== 'ENDED' && phase !== 'FAILED')) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      setLiveError('Microphone unavailable: unsupported browser or insecure context');
      setPhaseBoth('FAILED');
      return;
    }
    setStarting(true);
    setLiveError(null);
    setWindows([]);
    setLiveSession(null);
    setConnectMs(null);
    setPhaseBoth('CREATING');
    try {
      // 1. Backend-owned session first (authoritative session_id).
      let snap: LiveSessionSnapshot;
      try {
        snap = await createLiveSession({
          callerId: callerId.trim() || '+910000000000',
          claimedIdentity: claimedIdentity.trim() || undefined,
          languageHint,
        });
      } catch {
        throw new Error('Real-time gateway unavailable');
      }
      sessionIdRef.current = snap.session_id;
      setLiveSession(snap);

      // 2. Real microphone (explicit user gesture already happened: this click).
      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (e) {
        throw new Error(micErrorMessage(e));
      }
      streamRef.current = stream;
      startLevelMeter(stream);

      // 3. WebRTC signaling: SDP offer → answer (single round-trip).
      setPhaseBoth('CONNECTING');
      const pc = new RTCPeerConnection();
      pcRef.current = pc;
      for (const track of stream.getTracks()) pc.addTrack(track, stream);
      pc.addEventListener('connectionstatechange', () => {
        if (pc.connectionState === 'connected') {
          setPhaseBoth('CONNECTED');
          if (offerStartRef.current) setConnectMs(Math.round(performance.now() - offerStartRef.current));
        } else if (pc.connectionState === 'failed') {
          setLiveError('WebRTC connection failed');
          setPhaseBoth('FAILED');
        }
      });
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      offerStartRef.current = performance.now();
      let answer: { sdp: string; type: RTCSdpType };
      try {
        answer = (await postLiveOffer(snap.session_id, offer.sdp || '', offer.type)) as { sdp: string; type: RTCSdpType };
      } catch (e) {
        throw new Error(e instanceof Error ? `Signaling failure: ${e.message}` : 'Signaling failure');
      }
      await pc.setRemoteDescription(new RTCSessionDescription(answer));

      // 4. Live events (WS primary, polling fallback — both backend-owned).
      const ws = new WebSocket(liveEventsUrl(snap.session_id));
      wsRef.current = ws;
      ws.onmessage = (msg) => {
        try { handleEvent(JSON.parse(String(msg.data)) as LiveEvent); }
        catch { /* ignore malformed frames */ }
      };
      ws.onerror = () => {
        window.clearInterval(pollRef.current);
        pollRef.current = window.setInterval(() => void pollSnapshot(snap.session_id), 3000);
      };
      ws.onclose = () => {
        if (phaseRef.current === 'CONNECTING' || phaseRef.current === 'CONNECTED'
          || phaseRef.current === 'RECEIVING' || phaseRef.current === 'PROCESSING') {
          window.clearInterval(pollRef.current);
          pollRef.current = window.setInterval(() => void pollSnapshot(snap.session_id), 3000);
        }
      };
    } catch (e) {
      setLiveError(e instanceof Error ? e.message : 'Real-time gateway unavailable');
      setPhaseBoth('FAILED');
      stopLocalMedia();
    } finally {
      setStarting(false);
    }
  }, [starting, phase, callerId, claimedIdentity, languageHint, startLevelMeter, handleEvent, pollSnapshot, stopLocalMedia]);

  const endLiveCall = useCallback(async () => {
    const sid = sessionIdRef.current;
    window.clearInterval(pollRef.current);
    if (sid) {
      try {
        const snap = await endLiveSession(sid);
        setLiveSession(snap);
        setWindows(snap.windows);
        if (snap.final_status === 'complete') setPhaseBoth('ANALYSIS');
        else setPhaseBoth('ENDED');
      } catch {
        setPhaseBoth('ENDED');
      }
      sessionIdRef.current = null;
    } else {
      setPhaseBoth('ENDED');
    }
    stopLocalMedia();
    void refresh();
  }, [refresh, stopLocalMedia]);

  const handleAnalyze = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      setError('Select an audio file (WAV/MP3/OGG/FLAC) to analyze.');
      return;
    }
    setAnalyzing(true);
    setError(null);
    try {
      const detail = await analyzeUpload({
        callerId: callerId.trim() || '+910000000000',
        claimedIdentity: claimedIdentity.trim() || undefined,
        languageHint,
        file,
      });
      await refresh();
      selection.openSession(detail.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analysis failed');
    } finally {
      setAnalyzing(false);
    }
  };

  const liveActive = phase === 'CONNECTING' || phase === 'CONNECTED'
    || phase === 'RECEIVING' || phase === 'PROCESSING' || phase === 'CREATING';
  const finalResultId = liveSession?.result_session_id ?? null;

  return (
    <div>
      <PageHeader title="Live Call Monitoring" subtitle="Real microphone → WebRTC → secure gateway → analysis windows.">
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
          color: gatewayReachable ? '#20d870' : '#f03838',
          background: gatewayReachable ? '#082010' : '#2a0808',
          border: `1px solid ${gatewayReachable ? '#20d87050' : '#f0383850'}`,
          padding: '2px 8px', borderRadius: 4,
        }}>
          {gatewayReachable === null ? '○ CHECKING…' : gatewayReachable ? '● LIVE BACKEND' : '○ REAL-TIME GATEWAY UNAVAILABLE'}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#20d870', fontWeight: 600 }}>
          <PulsingDot color="#20d870" />
          {calls.length} Active Sessions
        </div>
      </PageHeader>

      {/* Real live-call workflow: mic → WebRTC → gateway session */}
      <Card style={{ padding: '16px 20px', marginBottom: 20 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 12 }}>
          Live Call (Real Microphone)
        </div>
        {phase === 'IDLE' || phase === 'ENDED' || phase === 'FAILED' ? (
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <Btn onClick={() => void startLiveCall()} disabled={starting}>
              {starting ? 'Starting…' : 'Start Live Call'}
            </Btn>
            {phase === 'FAILED' && liveError && (
              <span style={{ fontSize: 12, color: '#f03838' }}>{liveError}</span>
            )}
            {phase === 'ENDED' && (
              <span style={{ fontSize: 12, color: '#6280b8' }}>Call ended. Microphone released.</span>
            )}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{
                fontSize: 11, fontWeight: 700, letterSpacing: '0.06em',
                color: '#20d870', background: '#082010',
                border: '1px solid #20d87050', padding: '3px 8px', borderRadius: 4,
              }}>
                ● LIVE · {PHASE_LABEL[phase].toUpperCase()}
              </span>
              {liveSession && (
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6280b8' }}>
                  session {liveSession.session_id}
                </span>
              )}
              {connectMs != null && (
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#3a4e78' }}>
                  connected in {connectMs} ms (measured)
                </span>
              )}
              <span style={{ marginLeft: 'auto' }}>
                <Btn variant="danger" size="sm" onClick={() => void endLiveCall()}>End Call</Btn>
              </span>
            </div>
            {/* Audio activity from the real microphone (AnalyserNode RMS). */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 11, color: '#3a4e78', width: 90 }}>Mic level</span>
              <div style={{ flex: 1, height: 6, background: '#18234a', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${audioLevel}%`, background: '#20d870', borderRadius: 3, transition: 'width 120ms' }} />
              </div>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6280b8', width: 30, textAlign: 'right' }}>{audioLevel}</span>
            </div>
            {liveSession && (
              <div style={{ fontSize: 12, color: '#6280b8' }}>
                Audio received: {liveSession.audio_seconds_received}s · windows processed: {liveSession.windows_processed}
                {liveSession.final_status === 'processing' && ' · final risk analysis running…'}
              </div>
            )}
            {windows.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 4 }}>
                {windows.map(w => (
                  <div key={w.window_index} style={{
                    padding: '8px 12px', borderRadius: 6, background: '#080c24',
                    border: '1px solid #18234a', fontSize: 12, color: '#a0b8e0',
                  }}>
                    Analysis window #{w.window_index + 1} processed — {w.audio_s}s audio ·{' '}
                    <span style={{ color: '#d5dffa', fontWeight: 600 }}>{w.risk_level} → {w.action}</span>{' '}
                    <span style={{ color: '#3a4e78' }}>({w.detection_summary}) · measured {w.latency_ms} ms</span>
                  </div>
                ))}
              </div>
            )}
            {phase === 'ANALYSIS' && (
              <div style={{
                padding: '10px 14px', borderRadius: 8, background: '#082010',
                border: '1px solid #20d87050', fontSize: 13, color: '#20d870', fontWeight: 600,
              }}>
                Risk analysis available
                {finalResultId && (
                  <button
                    onClick={() => selection.openSession(finalResultId)}
                    style={{
                      marginLeft: 12, padding: '6px 12px', background: '#0f2050',
                      border: '1px solid #2a4080', borderRadius: 6, color: '#90b8f8',
                      fontSize: 12, fontWeight: 600, cursor: 'pointer',
                    }}
                  >
                    View Session →
                  </button>
                )}
              </div>
            )}
            {liveError && (
              <div style={{ fontSize: 12, color: '#f07228' }}>{liveError}</div>
            )}
          </div>
        )}
      </Card>

      {/* Telephony ingress — real SIP/RTP or provider calls only, never demo data */}
      <Card style={{ padding: '16px 20px', marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            Telephony Ingress (SIP / RTP)
          </div>
          <span style={{
            fontSize: 10, fontWeight: 700, letterSpacing: '0.08em',
            color: telephonyStatus?.transports.local_rtp.listening ? '#20d870' : '#f5a020',
            background: telephonyStatus?.transports.local_rtp.listening ? '#082010' : '#2a1e06',
            border: `1px solid ${telephonyStatus?.transports.local_rtp.listening ? '#20d87050' : '#f5a02050'}`,
            padding: '2px 8px', borderRadius: 4,
          }}>
            {telephonyStatus == null
              ? '○ STATUS UNKNOWN'
              : !telephonyStatus.provider_configured && !telephonyStatus.transports.local_rtp.enabled
                ? '○ TELEPHONY UNAVAILABLE'
                : telephonyStatus.transports.local_rtp.listening
                  ? `● LOCAL RTP ${telephonyStatus.transports.local_rtp.host}:${telephonyStatus.transports.local_rtp.port}`
                  : '○ RTP NOT LISTENING'}
          </span>
          {telephonyStatus != null && (
            <span style={{ fontSize: 11, color: '#3a4e78' }}>
              provider: {telephonyStatus.provider_configured ? telephonyStatus.provider : 'not configured'}
              {' · '}ari: {telephonyStatus.ari.configured ? `${telephonyStatus.ari.state} (${telephonyStatus.ari.active_taps} taps)` : 'not configured'}
            </span>
          )}
        </div>
        {gatewayReachable === false || telephonyStatus == null ? (
          <div style={{ fontSize: 12, color: '#f03838' }}>
            Real-time gateway unavailable — telephony ingress state cannot be read.
          </div>
        ) : telephonyCalls.length === 0 ? (
          <div style={{ fontSize: 12, color: '#6280b8' }}>
            No telephony calls. Point a real SIP phone at {telephonyStatus.transports.local_rtp.host}:{telephonyStatus.transports.local_rtp.port} (PCMU/PCMA) or configure a provider — sessions appear here only when genuine call media arrives.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {telephonyCalls.map(call => (
              <div key={call.session_id} style={{
                display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center',
                padding: '8px 12px', borderRadius: 6, background: '#080c24',
                border: '1px solid #18234a', fontSize: 12,
              }}>
                <span style={{
                  fontSize: 10, fontWeight: 700, letterSpacing: '0.06em',
                  color: '#4080f8', background: '#0a1a38',
                  border: '1px solid #4080f850', padding: '2px 7px', borderRadius: 4,
                }}>
                  {call.transport === 'local-rtp' ? 'TELEPHONY/SIP' : call.transport === 'asterisk-ari' ? 'TELEPHONY/PBX' : 'TELEPHONY/PROVIDER'}
                </span>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", color: '#d5dffa' }}>
                  {call.session_id.slice(0, 8)}
                </span>
                <span style={{ color: '#20d870', fontWeight: 600 }}>{call.state}</span>
                {call.latest_action ? (
                  <span style={{ color: '#f5a020', fontWeight: 600 }}>decision {call.latest_action}</span>
                ) : (
                  <span style={{ color: '#3a4e78' }}>no analysis yet</span>
                )}
                {call.latest_action && (
                  <span style={{ color: '#f5a020', fontWeight: 600 }}>action {call.latest_action}</span>
                )}
                <span style={{ color: '#6280b8' }}>caller {call.caller_display}</span>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", color: '#6280b8' }}>
                  {call.audio_seconds}s · {call.stats.packets_received} pkts
                  {call.stats.packets_lost > 0 && ` · ${call.stats.packets_lost} lost`}
                  {call.stats.codec && ` · ${call.stats.codec}`}
                </span>
                <button
                  onClick={() => void openTelephonyAnalysis(call)}
                  style={{
                    marginLeft: 'auto', padding: '5px 12px', background: '#0f2050',
                    border: '1px solid #2a4080', borderRadius: 6, color: '#90b8f8',
                    fontSize: 12, fontWeight: 600, cursor: 'pointer',
                  }}
                >
                  View Analysis →
                </button>
              </div>
            ))}
          </div>
        )}
        {telephonyNote && <div style={{ marginTop: 8, fontSize: 12, color: '#f07228' }}>{telephonyNote}</div>}
      </Card>

      {/* Analyze upload — posts to POST /api/v1/sessions/analyze */}
      <Card style={{ padding: '16px 20px', marginBottom: 20 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 12 }}>
          Analyze New Call Recording
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            value={callerId}
            onChange={e => setCallerId(e.target.value)}
            placeholder="Caller ID"
            style={{ padding: '8px 12px', background: '#080c24', border: '1px solid #18234a', borderRadius: 6, color: '#d5dffa', fontSize: 13, width: 180 }}
          />
          <input
            value={claimedIdentity}
            onChange={e => setClaimedIdentity(e.target.value)}
            placeholder="Claimed identity (optional)"
            style={{ padding: '8px 12px', background: '#080c24', border: '1px solid #18234a', borderRadius: 6, color: '#d5dffa', fontSize: 13, width: 220 }}
          />
          <select
            value={languageHint}
            onChange={e => setLanguageHint(e.target.value)}
            title="Language hint for ASR"
            style={{ padding: '8px 12px', background: '#080c24', border: '1px solid #18234a', borderRadius: 6, color: '#d5dffa', fontSize: 13 }}
          >
            {['EN', 'HI', 'TA', 'TE', 'ML', 'KN'].map(l => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
          <input ref={fileRef} type="file" accept="audio/*,.wav,.mp3,.ogg,.flac" style={{ fontSize: 12, color: '#6280b8' }} />
          <Btn onClick={handleAnalyze} disabled={analyzing}>{analyzing ? 'Analyzing…' : 'Analyze Call →'}</Btn>
        </div>
        {error && <div style={{ marginTop: 10, fontSize: 12, color: '#f03838' }}>{error}</div>}
        {gatewayReachable === false && (
          <div style={{ marginTop: 10, fontSize: 12, color: '#f03838' }}>
            Real-time gateway unavailable — start it with <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>uvicorn gateway.app:app --host 127.0.0.1 --port 8000</span> to analyze real audio.
          </div>
        )}
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
        {loading && (
          <div style={{ gridColumn: '1 / -1', padding: '32px', textAlign: 'center', color: '#6280b8', fontSize: 13 }}>
            Loading live sessions…
          </div>
        )}
        {!loading && gatewayReachable === false && (
          <div style={{ gridColumn: '1 / -1', padding: '12px 16px', borderRadius: 8, background: '#2a0808', border: '1px solid #f0383840', fontSize: 12, color: '#f03838' }}>
            Real-time gateway unavailable. No sessions to display.
          </div>
        )}
        {!loading && gatewayReachable === true && calls.length === 0 && (
          <div style={{ gridColumn: '1 / -1', padding: '32px', textAlign: 'center', color: '#3a4e78', fontSize: 13 }}>
            No sessions yet — upload a call recording above or start a live call to run the real pipeline.
          </div>
        )}
        {!loading && gatewayReachable === true && calls.map(call => {
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
                <span style={{ marginLeft: 'auto' }}><RiskBadge score={call.risk} /></span>
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
                onClick={() => selection.openSession(call.id)}
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
