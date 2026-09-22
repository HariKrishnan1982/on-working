import type { CSSProperties, ReactNode } from 'react';

// ─── Risk helpers ────────────────────────────────────────────────────────────

export function riskColor(score: number): string {
  if (score >= 80) return '#f03838';
  if (score >= 60) return '#f07228';
  if (score >= 30) return '#f5a020';
  return '#20d870';
}
export function riskBg(score: number): string {
  if (score >= 80) return '#2a0808';
  if (score >= 60) return '#2a1408';
  if (score >= 30) return '#2a1e06';
  return '#082010';
}
export function riskLabel(score: number): string {
  if (score >= 80) return 'CRITICAL';
  if (score >= 60) return 'HIGH';
  if (score >= 30) return 'MEDIUM';
  return 'LOW';
}

// ─── Badges ──────────────────────────────────────────────────────────────────

export function RiskBadge({ score }: { score: number }) {
  return (
    <span style={{
      fontFamily: "'JetBrains Mono', monospace",
      fontSize: 12, fontWeight: 600,
      color: riskColor(score),
      background: riskBg(score),
      border: `1px solid ${riskColor(score)}50`,
      padding: '2px 7px', borderRadius: 4,
      whiteSpace: 'nowrap',
    }}>
      {score}
    </span>
  );
}

type ActionType = 'BLOCKED' | 'ALLOWED' | 'MFA' | 'MFA REQUIRED' | 'CALLBACK' | string;

const ACTION_STYLES: Record<string, { color: string; bg: string }> = {
  BLOCKED:      { color: '#f03838', bg: '#2a0808' },
  ALLOWED:      { color: '#20d870', bg: '#082010' },
  MFA:          { color: '#f07228', bg: '#2a1408' },
  'MFA REQUIRED': { color: '#f07228', bg: '#2a1408' },
  CALLBACK:     { color: '#f5a020', bg: '#2a1e06' },
  ALLOW:        { color: '#20d870', bg: '#082010' },
  BLOCK:        { color: '#f03838', bg: '#2a0808' },
};

export function ActionBadge({ action }: { action: ActionType }) {
  const s = ACTION_STYLES[action] ?? { color: '#6280b8', bg: '#0e1233' };
  return (
    <span style={{
      fontSize: 11, fontWeight: 700, letterSpacing: '0.06em',
      color: s.color, background: s.bg,
      border: `1px solid ${s.color}50`,
      padding: '2px 8px', borderRadius: 4, whiteSpace: 'nowrap',
    }}>
      {action}
    </span>
  );
}

export function ServiceBadge({ status }: { status: 'ONLINE' | 'CONNECTED' | 'OFFLINE' | 'HEALTHY' | string }) {
  const map: Record<string, { color: string; bg: string }> = {
    ONLINE:    { color: '#20d870', bg: '#082010' },
    CONNECTED: { color: '#4080f8', bg: '#0a1a38' },
    HEALTHY:   { color: '#20d870', bg: '#082010' },
    OFFLINE:   { color: '#f03838', bg: '#2a0808' },
    WARNING:   { color: '#f5a020', bg: '#2a1e06' },
  };
  const s = map[status] ?? { color: '#6280b8', bg: '#0e1233' };
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, letterSpacing: '0.06em',
      color: s.color, background: s.bg,
      border: `1px solid ${s.color}50`,
      padding: '2px 8px', borderRadius: 4,
    }}>
      {status}
    </span>
  );
}

// ─── MetricCard ───────────────────────────────────────────────────────────────

interface MetricCardProps {
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
  onClick?: () => void;
}

export function MetricCard({ label, value, sub, accent, onClick }: MetricCardProps) {
  return (
    <div
      onClick={onClick}
      style={{
        background: '#0e1233',
        border: '1px solid #18234a',
        borderRadius: 10,
        padding: '16px 20px',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'border-color 0.15s',
        minWidth: 0,
      }}
      onMouseEnter={e => onClick && ((e.currentTarget as HTMLDivElement).style.borderColor = '#2a3a70')}
      onMouseLeave={e => onClick && ((e.currentTarget as HTMLDivElement).style.borderColor = '#18234a')}
    >
      <div style={{ fontSize: 11, fontWeight: 500, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color: accent ?? '#d5dffa', fontFamily: "'JetBrains Mono', monospace", lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: '#6280b8', marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

// ─── PageHeader ───────────────────────────────────────────────────────────────

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: subtitle ? 4 : 0 }}>
        <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#d5dffa', letterSpacing: '-0.01em' }}>{title}</h1>
        {children && <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>{children}</div>}
      </div>
      {subtitle && <p style={{ margin: 0, fontSize: 13, color: '#6280b8' }}>{subtitle}</p>}
    </div>
  );
}

// ─── Card ─────────────────────────────────────────────────────────────────────

export function Card({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={{
      background: '#0e1233',
      border: '1px solid #18234a',
      borderRadius: 10,
      ...style,
    }}>
      {children}
    </div>
  );
}

// ─── SectionTitle ─────────────────────────────────────────────────────────────

export function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <div style={{ fontSize: 11, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 12 }}>
      {children}
    </div>
  );
}

// ─── Btn ──────────────────────────────────────────────────────────────────────

interface BtnProps {
  children: ReactNode;
  onClick?: () => void;
  variant?: 'primary' | 'ghost' | 'danger';
  size?: 'sm' | 'md';
  disabled?: boolean;
  style?: CSSProperties;
}

export function Btn({ children, onClick, variant = 'primary', size = 'md', disabled, style }: BtnProps) {
  const vars: Record<string, { bg: string; color: string; border: string; hover: string }> = {
    primary: { bg: '#1e4090', color: '#a0c0f8', border: '#2a5acc', hover: '#254aac' },
    ghost:   { bg: 'transparent', color: '#6280b8', border: '#18234a', hover: '#0e1838' },
    danger:  { bg: '#2a0808', color: '#f03838', border: '#50100a', hover: '#381010' },
  };
  const v = vars[variant];
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        background: v.bg, color: v.color, border: `1px solid ${v.border}`,
        padding: size === 'sm' ? '5px 12px' : '8px 16px',
        borderRadius: 6, fontSize: size === 'sm' ? 12 : 13, fontWeight: 500,
        cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1,
        transition: 'all 0.15s',
        ...style,
      }}
      onMouseEnter={e => !disabled && ((e.currentTarget as HTMLButtonElement).style.background = v.hover)}
      onMouseLeave={e => !disabled && ((e.currentTarget as HTMLButtonElement).style.background = v.bg)}
    >
      {children}
    </button>
  );
}

// ─── Table utilities ──────────────────────────────────────────────────────────

export function TableHeader({ cols }: { cols: string[] }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: `repeat(${cols.length}, 1fr)`,
      padding: '8px 16px',
      borderBottom: '1px solid #18234a',
    }}>
      {cols.map(c => (
        <span key={c} style={{ fontSize: 10, fontWeight: 600, color: '#3a4e78', letterSpacing: '0.1em', textTransform: 'uppercase' }}>{c}</span>
      ))}
    </div>
  );
}

// ─── StatusPill ───────────────────────────────────────────────────────────────

export function StatusPill({ label, color }: { label: string; color: string }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      fontSize: 11, fontWeight: 600, color, letterSpacing: '0.04em',
    }}>
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: color, flexShrink: 0 }} />
      {label}
    </span>
  );
}

// ─── Risk Gauge SVG ───────────────────────────────────────────────────────────

export function RiskGauge({ score }: { score: number }) {
  const r = 72, cx = 100, cy = 92;
  const color = riskColor(score);
  const label = riskLabel(score);

  const angle = Math.PI * (1 - score / 100);
  const ex = cx + r * Math.cos(angle);
  const ey = cy - r * Math.sin(angle);

  const largeArc = score > 50 ? 1 : 0;

  return (
    <svg viewBox="0 0 200 112" style={{ width: '100%', maxWidth: 240, display: 'block' }}>
      {/* Track */}
      <path
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
        fill="none" stroke="#18234a" strokeWidth="14" strokeLinecap="round"
      />
      {/* Progress */}
      {score > 0 && (
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 ${largeArc} 1 ${ex} ${ey}`}
          fill="none" stroke={color} strokeWidth="14" strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 6px ${color}60)` }}
        />
      )}
      {/* Score number */}
      <text x={cx} y={cy - 6} textAnchor="middle" fill={color}
        fontSize="38" fontWeight="700" fontFamily="'JetBrains Mono', monospace">
        {score}
      </text>
      <text x={cx} y={cy + 14} textAnchor="middle" fill="#3a4e78" fontSize="11" fontFamily="'Inter', sans-serif">
        / 100
      </text>
      <text x={cx} y={cy + 32} textAnchor="middle" fill={color}
        fontSize="12" fontWeight="700" fontFamily="'Inter', sans-serif" letterSpacing="2">
        {label}
      </text>
    </svg>
  );
}

// ─── BackButton ───────────────────────────────────────────────────────────────

export function BackButton({ onClick, label = 'Back' }: { onClick: () => void; label?: string }) {
  return (
    <button onClick={onClick} style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      background: 'transparent', border: 'none', cursor: 'pointer',
      color: '#6280b8', fontSize: 13, padding: '4px 0', marginBottom: 16,
    }}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M19 12H5M12 5l-7 7 7 7" />
      </svg>
      {label}
    </button>
  );
}
