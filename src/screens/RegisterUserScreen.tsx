import { useState } from 'react';
import type { NavigateFn } from '../App';
import { BackButton, Btn, Card, SectionTitle } from '../components/ui';

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

function VoiceSample({ n, recorded }: { n: number; recorded: boolean }) {
  const [active, setActive] = useState(false);
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 14,
      padding: '12px 16px', borderRadius: 8,
      background: recorded ? '#08200e' : '#0c1028',
      border: `1px solid ${recorded ? '#20d87050' : '#18234a'}`,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
        background: recorded ? '#0a2818' : active ? '#1a3060' : '#0e1838',
        border: `2px solid ${recorded ? '#20d870' : active ? '#4080f8' : '#28384a'}`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        cursor: 'pointer', transition: 'all 0.15s',
      }}
        onClick={() => setActive(!active)}
      >
        {recorded ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#20d870" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={active ? '#4080f8' : '#6280b8'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8" />
          </svg>
        )}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: recorded ? '#20d870' : '#d5dffa', marginBottom: 2 }}>Sample {n}</div>
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
        {recorded ? 'Recorded' : 'Pending'}
      </span>
    </div>
  );
}

export default function RegisterUserScreen({ navigate }: { navigate: NavigateFn }) {
  const [step, setStep] = useState<Step>(1);
  const [form, setForm] = useState({ name: '', email: '', role: '', dept: '', empId: '' });
  const [progress, setProgress] = useState(0);

  const handleNext = () => {
    if (step === 3) {
      let p = 0;
      const id = setInterval(() => {
        p += 5;
        setProgress(p);
        if (p >= 100) {
          clearInterval(id);
          setStep(4);
          setProgress(0);
        }
      }, 80);
    } else {
      setStep((step + 1) as Step);
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
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <Btn onClick={handleNext}>Continue to Voice Enrollment →</Btn>
            </div>
          </Card>
        )}

        {step === 2 && (
          <Card style={{ padding: '24px 28px' }}>
            <SectionTitle>Voice Enrollment</SectionTitle>
            <p style={{ fontSize: 13, color: '#6280b8', marginBottom: 20 }}>
              Record three voice samples for identity baseline. Ensure clear audio in a quiet environment.
              Read the provided phrase for each sample.
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 24 }}>
              <VoiceSample n={1} recorded={true} />
              <VoiceSample n={2} recorded={true} />
              <VoiceSample n={3} recorded={false} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Btn variant="ghost" onClick={() => setStep(1)}>← Back</Btn>
              <Btn onClick={handleNext}>Analyze Voice Features →</Btn>
            </div>
          </Card>
        )}

        {step === 3 && (
          <Card style={{ padding: '24px 28px' }}>
            <SectionTitle>Feature Extraction</SectionTitle>
            <p style={{ fontSize: 13, color: '#6280b8', marginBottom: 20 }}>
              AI models are extracting biometric voice features and building a secure identity profile.
            </p>
            {[
              { label: 'Wav2Vec2 Feature Extraction', value: 100 },
              { label: 'RawNet2 Speaker Embedding', value: 100 },
              { label: 'Prosody & Cadence Analysis', value: 100 },
              { label: 'Voice Quality Assessment', value: 98 },
              { label: 'Profile Synthesis', value: 100 },
            ].map(item => (
              <div key={item.label} style={{ marginBottom: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                  <span style={{ fontSize: 12, color: '#8090b0' }}>{item.label}</span>
                  <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: '#20d870' }}>{item.value}%</span>
                </div>
                <div style={{ height: 5, background: '#18234a', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${item.value}%`, background: '#20d870', borderRadius: 3 }} />
                </div>
              </div>
            ))}
            <div style={{ marginTop: 8, padding: '10px 14px', borderRadius: 8, background: '#082010', border: '1px solid #20d87040', marginBottom: 24 }}>
              <span style={{ fontSize: 12, color: '#20d870', fontWeight: 600 }}>✓ Voice Quality: EXCELLENT (98%)</span>
            </div>
            {progress > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: '#6280b8', marginBottom: 6 }}>Creating secure profile… {progress}%</div>
                <div style={{ height: 6, background: '#18234a', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${progress}%`, background: '#4080f8', borderRadius: 3, transition: 'width 0.1s' }} />
                </div>
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <Btn variant="ghost" onClick={() => setStep(2)}>← Back</Btn>
              <Btn onClick={handleNext} disabled={progress > 0}>Create Secure Profile →</Btn>
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
            <p style={{ color: '#6280b8', fontSize: 13, marginBottom: 24 }}>The user has been successfully enrolled in the VoiceShield security gateway.</p>

            <div style={{ background: '#080c24', border: '1px solid #18234a', borderRadius: 8, padding: '16px', marginBottom: 24, textAlign: 'left', maxWidth: 400, margin: '0 auto 24px' }}>
              {[
                { label: 'Profile ID', value: 'VP-048', mono: true },
                { label: 'User', value: form.name || 'New User' },
                { label: 'Employee ID', value: form.empId || 'EMP-0048', mono: true },
                { label: 'Enrolled', value: '2026-09-20 10:44:33 UTC', mono: true },
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
              <Btn onClick={() => { setStep(1); setForm({ name: '', email: '', role: '', dept: '', empId: '' }); }}>Enroll Another User</Btn>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
