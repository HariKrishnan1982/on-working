import { useRef, useState } from 'react';
import type { NavigateFn } from '../App';
import { BackButton, Btn, Card, SectionTitle } from '../components/ui';
import { enrollUser, type EnrollResult } from '../lib/api';

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

function VoiceSample({ n, fileName }: { n: number; fileName: string | null }) {
  const recorded = fileName !== null;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 14,
      padding: '12px 16px', borderRadius: 8,
      background: recorded ? '#08200e' : '#0c1028',
      border: `1px solid ${recorded ? '#20d87050' : '#18234a'}`,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
        background: recorded ? '#0a2818' : '#0e1838',
        border: `2px solid ${recorded ? '#20d870' : '#28384a'}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'all 0.15s',
      }}>
        {recorded ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#20d870" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6280b8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8" />
          </svg>
        )}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: recorded ? '#20d870' : '#d5dffa', marginBottom: 2 }}>
          Sample {n}{fileName ? ` — ${fileName}` : ''}
        </div>
        {/* Waveform placeholder */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 1, height: 16 }}>
          {Array.from({ length: 28 }, (_, i) => (
            <div key={i} style={{
              width: 2, borderRadius: 1,
              height: recorded ? `${4 + Math.sin(i * 0.8) * 4 + 4}px` : '4px',
              background: recorded ? '#20d870' : '#18234a',
              transition: 'all 0.3s',
            }} />
          ))}
        </div>
      </div>
      <span style={{ fontSize: 11, color: recorded ? '#20d870' : '#3a4e78', fontWeight: 600 }}>
        {recorded ? 'Selected' : 'Pending'}
      </span>
    </div>
  );
}

export default function RegisterUserScreen({ navigate }: { navigate: NavigateFn }) {
  const [step, setStep] = useState<Step>(1);
  const [form, setForm] = useState({ name: '', email: '', role: '', dept: '', empId: '' });
  const [samples, setSamples] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<EnrollResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFiles = () => {
    const files = fileRef.current?.files;
    if (files) setSamples(Array.from(files).slice(0, 3));
  };

  const handleEnroll = async () => {
    if (!form.name.trim() || !form.empId.trim()) {
      setError('Full name and employee ID are required.');
      return;
    }
    if (samples.length === 0) {
      setError('Attach at least one voice sample (WAV/MP3/OGG/FLAC).');
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
        samples,
      });
      setResult(res);
      setStep(4);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Enrollment failed');
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
              Upload 1–3 voice samples for the ECAPA-TDNN biometric baseline.
              Files are stored under <span style={{ fontFamily: "'JetBrains Mono', monospace" }}>storage/profile_audio/</span> and
              the embedding is Fernet-encrypted at rest (POST /api/v1/users).
            </p>
            <div style={{
              padding: '12px 16px', borderRadius: 8, marginBottom: 20,
              background: '#0a1428', border: '1px solid #2040a050',
            }}>
              <div style={{ fontSize: 11, color: '#3a4e78', marginBottom: 4 }}>Enrollment Phrase</div>
              <div style={{ fontSize: 14, color: '#a0b8e0', fontStyle: 'italic' }}>
                "The security gateway verifies all authorized voice interactions in real time."
              </div>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="audio/*,.wav,.mp3,.ogg,.flac"
              multiple
              onChange={handleFiles}
              style={{ fontSize: 12, color: '#6280b8', marginBottom: 12 }}
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 24 }}>
              {[1, 2, 3].map(n => (
                <VoiceSample key={n} n={n} fileName={samples[n - 1]?.name ?? null} />
              ))}
            </div>
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
              { label: 'Voice samples', value: samples.length > 0 ? samples.map(s => s.name).join(', ') : 'none selected' },
              { label: 'Model', value: 'ecapa-tdnn-voxceleb-v0' },
            ].map(item => (
              <div key={item.label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                <span style={{ fontSize: 12, color: '#3a4e78' }}>{item.label}</span>
                <span style={{ fontSize: 12, color: '#d5dffa', fontFamily: "'JetBrains Mono', monospace" }}>{item.value}</span>
              </div>
            ))}
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
              <Btn onClick={() => { setStep(1); setResult(null); setSamples([]); setForm({ name: '', email: '', role: '', dept: '', empId: '' }); }}>Enroll Another User</Btn>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
