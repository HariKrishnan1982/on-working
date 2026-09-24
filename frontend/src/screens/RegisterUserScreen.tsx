import { useEffect, useRef, useState } from 'react';
import type { NavigateFn } from '../App';
import { BackButton, Btn, Card, SectionTitle } from '../components/ui';
import { enrollUser, type EnrollResult } from '../lib/api';
import {
  friendlyMicError,
  isRecordingSupported,
  pickRecordingMimeType,
  probeFileDurationS,
  recordingToWavFile,
} from '../lib/recorder';
import {
  ENROLLMENT_PHASES,
  PHASE_STATUS_LABEL,
  type PhaseStatus,
} from '../lib/enrollment';

type Step = 1 | 2 | 3 | 4;

const STEPS = [
  { n: 1, label: 'User Information' },
  { n: 2, label: 'Voice Enrollment' },
  { n: 3, label: 'Feature Extraction' },
  { n: 4, label: 'Profile Created' },
];

function StepIndicator({ current }: { current: Step }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0, marginBottom: 32 }}>
      {STEPS.map((s, i) => {
        const done = s.n < current;
        const active = s.n === current;
        return (
          <div key={s.n} style={{ display: 'flex', alignItems: 'center', flex: i < STEPS.length - 1 ? 1 : undefined }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
              <div style={{
                width: 32, height: 32, borderRadius: '50%',
                background: done ? '#1a4090' : active ? '#2060d8' : '#0c1233',
                border: `2px solid ${done || active ? '#4080f8' : '#18234a'}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700,
                color: done || active ? '#a0c8f8' : '#3a4e78',
              }}>
                {done ? (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#a0c8f8" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                ) : s.n}
              </div>
              <span style={{ fontSize: 10, color: active ? '#90b8f8' : '#3a4e78', fontWeight: active ? 600 : 400, whiteSpace: 'nowrap' }}>{s.label}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div style={{ flex: 1, height: 1, background: s.n < current ? '#4080f8' : '#18234a', margin: '0 8px', marginBottom: 20 }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function FormField({ label, placeholder, type = 'text', value, onChange }: {
  label: string; placeholder: string; type?: string;
  value: string; onChange: (v: string) => void;
}) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>
        {label}
      </label>
      <input
        type={type} value={value} onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        style={{
          width: '100%', padding: '9px 12px',
          background: '#080c24', border: '1px solid #18234a',
          borderRadius: 6, color: '#d5dffa', fontSize: 13, outline: 'none',
          transition: 'border-color 0.15s',
        }}
        onFocus={e => (e.target.style.borderColor = '#2a4a90')}
        onBlur={e => (e.target.style.borderColor = '#18234a')}
      />
    </div>
  );
}

/** One enrollment voice sample, either uploaded or recorded via microphone.
 *  Both paths converge to the same File representation submitted to
 *  POST /api/v1/users (`samples` multipart fields). Recordings stay local
 *  until the user clicks through Review & Enroll. */
interface SampleEntry {
  file: File;
  source: 'upload' | 'mic';
  durationS: number | null;
  url: string;
}

const EMPTY_SLOTS: (SampleEntry | null)[] = [null, null, null];

function formatDuration(s: number | null | undefined): string | null {
  if (s == null || !Number.isFinite(s)) return null;
  return `${s.toFixed(1)}s`;
}

function VoiceSampleCard({
  label,
  entry,
  isRecording,
  elapsedS,
  isConverting,
  canRecord,
  actionsLocked,
  onRecord,
  onStop,
  onRemove,
  onRetake,
}: {
  label: string;
  entry: SampleEntry | null;
  isRecording: boolean;
  elapsedS: number;
  isConverting: boolean;
  canRecord: boolean;
  actionsLocked: boolean;
  onRecord: () => void;
  onStop: () => void;
  onRemove: () => void;
  onRetake: () => void;
}) {
  const filled = entry !== null;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 14,
      padding: '12px 16px', borderRadius: 8,
      background: isRecording ? '#2a0808' : filled ? '#08200e' : '#0c1028',
      border: `1px solid ${isRecording ? '#f0383850' : filled ? '#20d87050' : '#18234a'}`,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
        background: filled && !isRecording ? '#0a2818' : '#0e1838',
        border: `2px solid ${isRecording ? '#f03838' : filled ? '#20d870' : '#28384a'}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'all 0.15s',
      }}>
        {filled && !isRecording ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#20d870" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={isRecording ? '#f03838' : '#6280b8'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8" />
          </svg>
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: filled ? '#20d870' : '#d5dffa', marginBottom: 2 }}>
          {label}{entry ? (entry.source === 'mic' ? ' — recorded from microphone' : ` — ${entry.file.name}`) : ''}
        </div>
        {isRecording ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '4px 0' }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%', background: '#f03838',
              display: 'inline-block',
            }} />
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: '#f03838' }}>
              Recording… {elapsedS.toFixed(1)}s
            </span>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 1, height: 16 }}>
            {Array.from({ length: 28 }, (_, i) => (
              <div key={i} style={{
                width: 2, borderRadius: 1,
                height: filled ? `${4 + Math.sin(i * 0.8) * 4 + 4}px` : '4px',
                background: filled ? '#20d870' : '#18234a',
                transition: 'all 0.3s',
              }} />
            ))}
          </div>
        )}
        {entry && !isRecording && (
          <div style={{ marginTop: 6 }}>
            <audio controls preload="metadata" src={entry.url} aria-label={`Playback ${label}`} style={{ width: '100%', height: 28, outline: 'none' }} />
            {formatDuration(entry.durationS) && (
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6280b8', marginTop: 2 }}>
                Duration: {formatDuration(entry.durationS)}
              </div>
            )}
          </div>
        )}
        {isConverting && (
          <div style={{ fontSize: 11, color: '#6280b8', marginTop: 4 }}>Processing recording…</div>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end', flexShrink: 0 }}>
        {isRecording ? (
          <Btn size="sm" variant="danger" onClick={onStop} aria-label="Stop Recording">■ Stop</Btn>
        ) : entry ? (
          <>
            <span style={{ fontSize: 11, color: '#20d870', fontWeight: 600 }}>Ready</span>
            <div style={{ display: 'flex', gap: 6 }}>
              <Btn size="sm" variant="ghost" onClick={onRetake} disabled={actionsLocked} aria-label={`Retake ${label}`}>Retake</Btn>
              <Btn size="sm" variant="ghost" onClick={onRemove} disabled={actionsLocked} aria-label={`Remove ${label}`}>Remove</Btn>
            </div>
          </>
        ) : isConverting ? (
          <span style={{ fontSize: 11, color: '#6280b8' }}>…</span>
        ) : (
          <>
            <Btn size="sm" variant="ghost" onClick={onRecord} disabled={!canRecord} aria-label={`Record ${label}`}>● Record</Btn>
            <span style={{ fontSize: 11, color: '#3a4e78', fontWeight: 600 }}>Pending</span>
          </>
        )}
      </div>
    </div>
  );
}

export default function RegisterUserScreen({ navigate }: { navigate: NavigateFn }) {
  const [step, setStep] = useState<Step>(1);
  const [form, setForm] = useState({ name: '', email: '', role: '', dept: '', empId: '' });
  // Fixed 3-slot sample list: uploads and mic recordings converge here as Files.
  const [slots, setSlots] = useState<(SampleEntry | null)[]>(EMPTY_SLOTS);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EnrollResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // ── Microphone recording refs (never stored in state) ─────────────────────
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const startStampRef = useRef(0);
  const slotsRef = useRef<(SampleEntry | null)[]>(EMPTY_SLOTS);
  const [activeSlot, setActiveSlot] = useState<number | null>(null);
  const [elapsedS, setElapsedS] = useState(0);
  const [convertingSlot, setConvertingSlot] = useState<number | null>(null);
  // Per-phase recording errors: a failure in one phase never clears the
  // completed samples of the other phases.
  const [phaseErrors, setPhaseErrors] = useState<(string | null)[]>([null, null, null]);
  // Currently displayed enrollment phase (dropdown selection).
  const [selectedPhase, setSelectedPhase] = useState(0);

  const sampleFiles = slots.filter((s): s is SampleEntry => s !== null).map(s => s.file);
  const completedCount = sampleFiles.length;
  const recorderBusy = activeSlot !== null || convertingSlot !== null;

  const setPhaseError = (slot: number, msg: string | null) => {
    setPhaseErrors(prev => {
      const next = [...prev];
      next[slot] = msg;
      return next;
    });
  };

  const phaseStatus = (idx: number): PhaseStatus => {
    if (activeSlot === idx) return 'recording';
    if (convertingSlot === idx) return 'processing';
    if (slots[idx] !== null) return 'recorded';
    if (phaseErrors[idx] !== null) return 'error';
    return 'pending';
  };

  // Global banner prefers the selected phase's error, then any other phase.
  const visibleRecError =
    phaseErrors[selectedPhase] ?? phaseErrors.find(e => e !== null) ?? null;

  const stopTimer = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const releaseStream = () => {
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
  };

  const abortRecording = () => {
    stopTimer();
    try {
      const rec = recorderRef.current;
      if (rec && rec.state !== 'inactive') rec.stop();
    } catch {
      /* recorder already torn down */
    }
    recorderRef.current = null;
    releaseStream();
    chunksRef.current = [];
    setActiveSlot(null);
    setConvertingSlot(null);
  };

  // Release mic + blob URLs on unmount / page leave (never auto-upload).
  useEffect(() => {
    const onBeforeUnload = () => {
      try {
        if (recorderRef.current && recorderRef.current.state !== 'inactive') {
          recorderRef.current.stop();
        }
      } catch {
        /* ignore during unload */
      }
      releaseStream();
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', onBeforeUnload);
      abortRecording();
      slotsRef.current.forEach(s => { if (s) URL.revokeObjectURL(s.url); });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setSlotEntry = (index: number, entry: SampleEntry | null) => {
    slotsRef.current = (() => {
      const next = [...slotsRef.current];
      const old = next[index];
      if (old) URL.revokeObjectURL(old.url);
      next[index] = entry;
      return next;
    })();
    setSlots(slotsRef.current);
  };

  const handleFiles = () => {
    const files = fileRef.current?.files;
    if (!files || files.length === 0) return;
    // Associate uploads with the selected phase first, then first empty phase.
    const preference = [selectedPhase, ...ENROLLMENT_PHASES.map(p => p.id)].filter(
      (v, i, a) => a.indexOf(v) === i,
    );
    const next = [...slotsRef.current];
    for (const f of Array.from(files)) {
      const emptyIdx = preference.find(idx => next[idx] === null);
      if (emptyIdx === undefined) {
        setError('All 3 phases already have samples — remove or retake one first.');
        break;
      }
      next[emptyIdx] = {
        file: f,
        source: 'upload',
        durationS: null,
        url: URL.createObjectURL(f),
      };
      setPhaseError(emptyIdx, null);
      // Probe duration asynchronously; failure keeps null (display only).
      void probeFileDurationS(f).then(d => {
        if (d == null) return;
        setSlots(cur => {
          const upd = [...cur];
          const curEntry = upd[emptyIdx];
          if (curEntry && curEntry.file === f) {
            const merged = { ...curEntry, durationS: d };
            upd[emptyIdx] = merged;
            slotsRef.current = upd;
          }
          return upd;
        });
      });
    }
    slotsRef.current = next;
    setSlots(next);
    setError(null);
    // Allow re-selecting the same file later.
    if (fileRef.current) fileRef.current.value = '';
  };

  const finalizeRecording = (slot: number, recorded: Blob) => {
    setConvertingSlot(slot);
    recordingToWavFile(recorded, `mic-sample-${slot + 1}.wav`)
      .then(({ file, durationS }) => {
        setSlotEntry(slot, {
          file,
          source: 'mic',
          durationS,
          url: URL.createObjectURL(file),
        });
        setError(null);
        setPhaseError(slot, null);
        // Advance the dropdown to the next incomplete phase. The microphone
        // is never activated automatically — the user still presses Record.
        const nextIncomplete = ENROLLMENT_PHASES.find(p => slotsRef.current[p.id] === null);
        if (nextIncomplete) setSelectedPhase(nextIncomplete.id);
      })
      .catch((e: unknown) => {
        setPhaseError(slot, e instanceof Error ? e.message : 'Could not process the recording. Please try again.');
      })
      .finally(() => setConvertingSlot(null));
  };

  const startRecording = async (slot: number) => {
    if (activeSlot !== null || convertingSlot !== null) return; // one recording at a time
    setPhaseError(slot, null);
    if (!isRecordingSupported()) {
      setPhaseError(slot, friendlyMicError(new DOMException('unsupported', 'NotSupportedError')));
      return;
    }
    if (typeof window !== 'undefined' && window.isSecureContext === false) {
      setPhaseError(slot, 'Microphone access requires a secure context (HTTPS or localhost). Use file upload instead.');
      return;
    }
    // Retake semantics: recording into an occupied slot replaces it on success.
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = pickRecordingMimeType();
      const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.ondataavailable = (ev: BlobEvent) => {
        if (ev.data && ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      recorder.onerror = () => {
        setPhaseError(slot, 'Recording failed unexpectedly. Please try again or use file upload.');
      };
      recorder.onstop = () => {
        stopTimer();
        const chunks = chunksRef.current;
        chunksRef.current = [];
        recorderRef.current = null;
        releaseStream();
        setActiveSlot(null);
        const type = recorder.mimeType || 'audio/webm';
        const blob = new Blob(chunks, { type });
        if (blob.size === 0) {
          setPhaseError(slot, 'Recording produced no audio data — please try again.');
          return;
        }
        finalizeRecording(slot, blob);
      };
      recorder.start();
      startStampRef.current = Date.now();
      setElapsedS(0);
      setActiveSlot(slot);
      timerRef.current = window.setInterval(() => {
        setElapsedS((Date.now() - startStampRef.current) / 1000);
      }, 250);
    } catch (e) {
      releaseStream();
      recorderRef.current = null;
      setPhaseError(slot, friendlyMicError(e));
    }
  };

  const stopRecording = () => {
    stopTimer();
    try {
      const rec = recorderRef.current;
      if (rec && rec.state !== 'inactive') rec.stop();
      else {
        releaseStream();
        setActiveSlot(null);
      }
    } catch {
      releaseStream();
      setActiveSlot(null);
    }
  };

  const resetAll = () => {
    abortRecording();
    slotsRef.current.forEach(s => { if (s) URL.revokeObjectURL(s.url); });
    slotsRef.current = EMPTY_SLOTS;
    setSlots(EMPTY_SLOTS);
    setResult(null);
    setError(null);
    setPhaseErrors([null, null, null]);
    setSelectedPhase(0);
    setForm({ name: '', email: '', role: '', dept: '', empId: '' });
  };

  const handleEnroll = async () => {
    if (!form.name.trim() || !form.empId.trim()) {
      setError('Full name and employee ID are required.');
      return;
    }
    if (sampleFiles.length === 0) {
      setError('Attach at least one voice sample (WAV/MP3/OGG/FLAC).');
      return;
    }
    if (activeSlot !== null || convertingSlot !== null) {
      setError('Wait for the active recording to finish before enrolling.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await enrollUser({
        name: form.name.trim(),
        empId: form.empId.trim(),
        email: form.email.trim(),
        role: form.role.trim(),
        dept: form.dept.trim(),
        samples: sampleFiles,
      });
      setResult(res);
      setStep(4);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Enrollment failed';
      // Surface the real backend contract distinctly: 409 = already enrolled,
      // 503 = ECAPA voiceprint extraction unavailable. Never fabricate success.
      if (/API 409/.test(msg)) {
        setError(`Speaker already enrolled (409): ${msg}`);
      } else if (/API 503/.test(msg)) {
        setError(`Voiceprint extraction unavailable (503, ECAPA offline): ${msg}`);
      } else {
        setError(msg);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <BackButton onClick={() => navigate('trusted-users')} label="Back to Trusted Users" />
      <h1 style={{ margin: '0 0 24px', fontSize: 20, fontWeight: 700, color: '#d5dffa' }}>Register New User</h1>

      <div style={{ maxWidth: 680, margin: '0 auto' }}>
        <StepIndicator current={step} />

        {step === 1 && (
          <Card style={{ padding: '24px 28px' }}>
            <SectionTitle>User Information</SectionTitle>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
              <FormField label="Full Name" placeholder="Alex Chen" value={form.name} onChange={v => setForm(f => ({ ...f, name: v }))} />
              <FormField label="Employee ID" placeholder="EMP-0041" value={form.empId} onChange={v => setForm(f => ({ ...f, empId: v }))} />
              <FormField label="Email Address" placeholder="a.chen@organization.gov" type="email" value={form.email} onChange={v => setForm(f => ({ ...f, email: v }))} />
              <FormField label="Role / Title" placeholder="Finance Manager" value={form.role} onChange={v => setForm(f => ({ ...f, role: v }))} />
              <FormField label="Department" placeholder="Treasury" value={form.dept} onChange={v => setForm(f => ({ ...f, dept: v }))} />
            </div>
            {error && <div style={{ fontSize: 12, color: '#f03838', marginBottom: 12 }}>{error}</div>}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Btn onClick={() => { setError(null); setStep(2); }}>Continue to Voice Enrollment →</Btn>
            </div>
          </Card>
        )}

        {step === 2 && (
          <Card style={{ padding: '24px 28px' }}>
            <SectionTitle>Voice Enrollment</SectionTitle>
            <p style={{ fontSize: 13, color: '#6280b8', marginBottom: 20 }}>
              Record or upload one sample per phase for the ECAPA-TDNN biometric baseline.
              Each phase has its own phrase — read it aloud while recording. Mic recordings are
              converted locally to 16 kHz WAV and stay in this browser until you enroll.
              Files are stored under <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>storage/profile_audio/</span> and
              the embedding is Fernet-encrypted at rest (POST /api/v1/users).
            </p>

            {/* Progress: X / 3 + per-phase status (text, not color-only) */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap',
              padding: '10px 14px', borderRadius: 8, marginBottom: 16,
              background: '#0a1428', border: '1px solid #18234a',
            }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: '#d5dffa' }}>
                Voice Samples {completedCount} / 3 completed
              </span>
              {ENROLLMENT_PHASES.map(p => {
                const st = phaseStatus(p.id);
                const dot = st === 'recorded' ? '#20d870' : st === 'recording' ? '#f03838'
                  : st === 'error' ? '#f07228' : st === 'processing' ? '#4080f8' : '#3a4e78';
                const mark = st === 'recorded' ? '✓' : st === 'recording' ? '●'
                  : st === 'error' ? '!' : st === 'processing' ? '…' : '○';
                const isCurrent = p.id === selectedPhase;
                return (
                  <button
                    key={p.id}
                    onClick={() => setSelectedPhase(p.id)}
                    disabled={recorderBusy}
                    title={`Select ${p.title}`}
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 6,
                      padding: '4px 10px', borderRadius: 20, cursor: recorderBusy ? 'not-allowed' : 'pointer',
                      background: isCurrent ? '#0f2050' : 'transparent',
                      border: `1px solid ${isCurrent ? '#2a4080' : '#18234a'}`,
                      color: isCurrent ? '#90b8f8' : '#6280b8', fontSize: 11, fontWeight: isCurrent ? 700 : 400,
                    }}
                  >
                    <span style={{ color: dot, fontWeight: 700 }}>{mark}</span>
                    {p.title} · {PHASE_STATUS_LABEL[st]}
                  </button>
                );
              })}
            </div>

            {/* Phase selector */}
            <label
              htmlFor="enrollment-phase"
              style={{ display: 'block', fontSize: 11, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}
            >
              Enrollment Phase
            </label>
            <select
              id="enrollment-phase"
              value={selectedPhase}
              disabled={recorderBusy}
              onChange={e => setSelectedPhase(Number(e.target.value))}
              style={{
                width: '100%', padding: '9px 12px', marginBottom: 16,
                background: '#080c24', border: '1px solid #18234a',
                borderRadius: 6, color: '#d5dffa', fontSize: 13, outline: 'none',
                cursor: recorderBusy ? 'not-allowed' : 'pointer',
              }}
            >
              {ENROLLMENT_PHASES.map(p => (
                <option key={p.id} value={p.id}>
                  {p.title} — {PHASE_STATUS_LABEL[phaseStatus(p.id)]}
                </option>
              ))}
            </select>

            {/* Selected phrase — always visible immediately before recording */}
            <div style={{
              padding: '12px 16px', borderRadius: 8, marginBottom: 16,
              background: '#0a1428', border: '1px solid #2040a050',
            }}>
              <div style={{ fontSize: 11, color: '#3a4e78', marginBottom: 4 }}>
                {ENROLLMENT_PHASES[selectedPhase].title.toUpperCase()} — READ THIS PHRASE ALOUD
              </div>
              <div style={{ fontSize: 14, color: '#a0b8e0', fontStyle: 'italic' }}>
                "{ENROLLMENT_PHASES[selectedPhase].phrase}"
              </div>
            </div>

            <label
              htmlFor="enrollment-upload"
              style={{ display: 'block', fontSize: 11, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}
            >
              Upload audio for {ENROLLMENT_PHASES[selectedPhase].title} (optional)
            </label>
            <input
              id="enrollment-upload"
              ref={fileRef}
              type="file"
              accept="audio/*,.wav,.mp3,.ogg,.flac"
              multiple
              disabled={recorderBusy}
              onChange={handleFiles}
              style={{ fontSize: 12, color: '#6280b8', marginBottom: 12 }}
            />
            {!isRecordingSupported() && (
              <div style={{
                padding: '8px 12px', borderRadius: 6, marginBottom: 12,
                background: '#2a1e06', border: '1px solid #f5a02040',
                fontSize: 11, color: '#f5a020',
              }}>
                Voice recording is not supported by this browser. Use file upload instead.
              </div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 12 }}>
              <VoiceSampleCard
                label={ENROLLMENT_PHASES[selectedPhase].title}
                entry={slots[selectedPhase]}
                isRecording={activeSlot === selectedPhase}
                elapsedS={elapsedS}
                isConverting={convertingSlot === selectedPhase}
                canRecord={!recorderBusy && isRecordingSupported()}
                actionsLocked={recorderBusy}
                onRecord={() => void startRecording(selectedPhase)}
                onStop={stopRecording}
                onRemove={() => setSlotEntry(selectedPhase, null)}
                onRetake={() => { setSlotEntry(selectedPhase, null); void startRecording(selectedPhase); }}
              />
            </div>
            {activeSlot !== null && (
              <div style={{ fontSize: 11, color: '#f03838', marginBottom: 12 }}>
                Recording {ENROLLMENT_PHASES[activeSlot].title}… {elapsedS.toFixed(1)}s — finish it before switching phase.
              </div>
            )}
            {visibleRecError && <div style={{ fontSize: 12, color: '#f07228', marginBottom: 12 }}>{visibleRecError}</div>}
            {error && <div style={{ fontSize: 12, color: '#f03838', marginBottom: 12 }}>{error}</div>}
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Btn variant="ghost" onClick={() => setStep(1)}>← Back</Btn>
              <Btn onClick={() => { setError(null); setStep(3); }}>Review & Enroll →</Btn>
            </div>
          </Card>
        )}

        {step === 3 && (
          <Card style={{ padding: '24px 28px' }}>
            <SectionTitle>Feature Extraction</SectionTitle>
            <p style={{ fontSize: 13, color: '#6280b8', marginBottom: 20 }}>
              ECAPA-TDNN extracts a 192-dim voiceprint, encrypts it with Fernet, and keys it by
              HMAC-SHA256 pseudonym. Only name/role/dept metadata is kept in the operator registry.
            </p>
            {[
              { label: 'Enrolling', value: `${form.name || '—'} (${form.empId || '—'})` },
              { label: 'Model', value: 'ecapa-tdnn-voxceleb-v0' },
            ].map(item => (
              <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                <span style={{ fontSize: 12, color: '#3a4e78' }}>{item.label}</span>
                <span style={{ fontSize: 12, color: '#d5dffa', fontFamily: "'JetBrains Mono', monospace" }}>{item.value}</span>
              </div>
            ))}
            <div style={{ fontSize: 10, fontWeight: 700, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase', margin: '16px 0 8px' }}>
              Voice Enrollment Review — {completedCount} / 3 phases recorded
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 8 }}>
              {ENROLLMENT_PHASES.map(p => {
                const entry = slots[p.id];
                const done = entry !== null;
                return (
                  <div key={p.id} style={{
                    padding: '10px 14px', borderRadius: 8,
                    background: done ? '#08200e' : '#0c1028',
                    border: `1px solid ${done ? '#20d87050' : '#18234a'}`,
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                      <span style={{ fontSize: 12, fontWeight: 700, color: done ? '#20d870' : '#3a4e78' }}>
                        {done ? '✓' : '○'} {p.title} — {done ? 'Recorded' : 'Not recorded (skipped)'}
                      </span>
                      {done && formatDuration(entry.durationS) && (
                        <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6280b8' }}>
                          Duration: {formatDuration(entry.durationS)}
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 12, color: '#a0b8e0', fontStyle: 'italic', marginBottom: 4 }}>
                      "{p.phrase}"
                    </div>
                    <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#6280b8' }}>
                      {done
                        ? `${entry.file.name} · ${entry.source === 'mic' ? 'mic → wav' : 'upload'} · ${(entry.file.size / 1024).toFixed(1)} KB`
                        : 'This phase will not be submitted.'}
                    </div>
                  </div>
                );
              })}
            </div>
            {error && <div style={{ fontSize: 12, color: '#f03838', margin: '12px 0' }}>{error}</div>}
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
              <Btn variant="ghost" onClick={() => setStep(2)}>← Back</Btn>
              <Btn onClick={handleEnroll} disabled={busy}>{busy ? 'Enrolling…' : 'Create Secure Profile →'}</Btn>
            </div>
          </Card>
        )}

        {step === 4 && (
          <Card style={{ padding: '36px 28px', textAlign: 'center' }}>
            <div style={{
              width: 64, height: 64, borderRadius: '50%', margin: '0 auto 20px',
              background: '#082010', border: '2px solid #20d870',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#20d870" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <h2 style={{ margin: '0 0 6px', fontSize: 20, fontWeight: 700, color: '#20d870' }}>Voice Profile Created</h2>
            <p style={{ color: '#6280b8', fontSize: 13, marginBottom: 24 }}>
              {result
                ? `Enrolled on the live backend — voiceprint encrypted, subject_ref …${result.subject_ref_last8}.`
                : 'The user has been successfully enrolled in the VoiceShield security gateway.'}
            </p>

            <div style={{ background: '#080c24', border: '1px solid #18234a', borderRadius: 8, padding: '16px', marginBottom: 24, textAlign: 'left', maxWidth: 400, margin: '0 auto 24px' }}>
              {[
                { label: 'Profile ID', value: result?.profile ?? 'VP-048', mono: true },
                { label: 'User', value: result?.name ?? form.name ?? 'New User' },
                { label: 'Employee ID', value: result?.emp_id ?? form.empId ?? 'EMP-0048', mono: true },
                { label: 'Enrolled', value: result?.enrolled ?? new Date().toISOString().slice(0, 10), mono: true },
                { label: 'Quality', value: result ? `${result.quality}%` : '—', mono: true },
                { label: 'Status', value: 'ACTIVE', color: '#20d870' },
              ].map(r => (
                <div key={r.label} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #0e1838' }}>
                  <span style={{ fontSize: 12, color: '#3a4e78' }}>{r.label}</span>
                  <span style={{ fontFamily: r.mono ? "'JetBrains Mono', monospace" : undefined, fontSize: 12, color: (r as { color?: string }).color ?? '#d5dffa' }}>{r.value}</span>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
              <Btn variant="ghost" onClick={() => navigate('trusted-users')}>Back to Users</Btn>
              <Btn onClick={resetAll}>Enroll Another User</Btn>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
