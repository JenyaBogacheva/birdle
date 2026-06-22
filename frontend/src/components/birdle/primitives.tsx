/**
 * Birdle AI — shared UI atoms, ported from the design's app/ui.jsx to TSX.
 * Theme tokens are read from CSS custom properties (see theme/birdleTheme.ts).
 */
import { useState, useEffect, type CSSProperties, type ReactNode } from 'react';

/* ---------- Icons (simple geometric line icons) ---------- */
type IconName =
  | 'search' | 'pin' | 'clock' | 'arrow' | 'check' | 'chevron'
  | 'info' | 'scope' | 'spark' | 'plus' | 'back' | 'bookmark';

interface IconProps {
  name: IconName;
  size?: number;
  stroke?: number;
  color?: string;
  style?: CSSProperties;
}

export function Icon({ name, size = 20, stroke = 1.6, color = 'currentColor', style }: IconProps) {
  const p = {
    width: size, height: size, viewBox: '0 0 24 24', fill: 'none',
    stroke: color, strokeWidth: stroke, strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const, style,
  };
  switch (name) {
    case 'search': return <svg {...p}><circle cx="11" cy="11" r="7" /><line x1="16.5" y1="16.5" x2="21" y2="21" /></svg>;
    case 'pin': return <svg {...p}><path d="M12 21s7-6.3 7-11a7 7 0 1 0-14 0c0 4.7 7 11 7 11Z" /><circle cx="12" cy="10" r="2.4" /></svg>;
    case 'clock': return <svg {...p}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>;
    case 'arrow': return <svg {...p}><line x1="4" y1="12" x2="19" y2="12" /><path d="M13 6l6 6-6 6" /></svg>;
    case 'check': return <svg {...p}><path d="M4 12.5l5 5L20 6.5" /></svg>;
    case 'chevron': return <svg {...p}><path d="M9 6l6 6-6 6" /></svg>;
    case 'info': return <svg {...p}><circle cx="12" cy="12" r="9" /><line x1="12" y1="11" x2="12" y2="16.5" /><circle cx="12" cy="7.6" r="0.6" fill={color} /></svg>;
    case 'scope': return <svg {...p}><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3.2" /></svg>;
    case 'spark': return <svg {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M18 6l-2.5 2.5M8.5 15.5L6 18" /></svg>;
    case 'plus': return <svg {...p}><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>;
    case 'back': return <svg {...p}><path d="M15 6l-6 6 6 6" /></svg>;
    case 'bookmark': return <svg {...p}><path d="M6 4h12v16l-6-4-6 4V4Z" /></svg>;
    default: return null;
  }
}

/* ---------- Brand mark + wordmark ---------- */
export function Brand({ light }: { light?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
      <span style={{ display: 'grid', placeItems: 'center', width: 30, height: 30, borderRadius: 9,
        background: light ? 'rgba(255,255,255,0.16)' : 'var(--accent)',
        border: light ? '1px solid rgba(255,255,255,0.4)' : 'none',
        color: light ? '#fff' : 'var(--accent-ink)', backdropFilter: 'blur(6px)' }}>
        <Icon name="scope" size={18} stroke={1.7} />
      </span>
      <span style={{ fontFamily: 'var(--font-display)', fontSize: 21, fontWeight: 540, letterSpacing: '-0.01em',
        color: light ? '#fff' : 'var(--ink)', lineHeight: 1,
        textShadow: light ? '0 1px 12px rgba(0,0,0,0.45)' : 'none' }}>Birdle</span>
    </div>
  );
}

/* ---------- Buttons ---------- */
interface PrimaryButtonProps {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  icon?: IconName | null;
  full?: boolean;
  type?: 'button' | 'submit';
}

export function PrimaryButton({ children, onClick, disabled, icon = 'arrow', full, type = 'button' }: PrimaryButtonProps) {
  const [h, setH] = useState(false);
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      onMouseEnter={() => setH(true)} onMouseLeave={() => setH(false)}
      style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 9,
        width: full ? '100%' : 'auto', padding: '15px 22px', borderRadius: 14, border: 'none',
        cursor: disabled ? 'default' : 'pointer', fontFamily: 'var(--font-body)', fontSize: 16, fontWeight: 600,
        letterSpacing: '0.01em', color: 'var(--accent-ink)', whiteSpace: 'nowrap',
        background: disabled ? 'color-mix(in oklch, var(--accent) 38%, #9a9a94)' : 'var(--accent)',
        boxShadow: disabled ? 'none' : (h ? '0 10px 26px -8px var(--accent-shadow)' : '0 6px 18px -10px var(--accent-shadow)'),
        transform: h && !disabled ? 'translateY(-1px)' : 'none',
        transition: 'transform .18s ease, box-shadow .22s ease, background .2s ease', opacity: disabled ? 0.8 : 1 }}>
      {children}{icon && <Icon name={icon} size={18} />}
    </button>
  );
}

interface ChipProps {
  children: ReactNode;
  onClick?: () => void;
  active?: boolean;
  tone?: 'default' | 'accent';
}

export function Chip({ children, onClick, active, tone = 'default' }: ChipProps) {
  const [h, setH] = useState(false);
  const base = tone === 'accent'
    ? { bg: active ? 'var(--accent)' : 'color-mix(in oklch, var(--accent) 12%, transparent)',
        col: active ? 'var(--accent-ink)' : 'var(--accent-strong)', bd: 'color-mix(in oklch, var(--accent) 34%, transparent)' }
    : { bg: h ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.62)', col: 'var(--ink)', bd: 'var(--hairline-strong)' };
  return (
    <button type="button" onClick={onClick} onMouseEnter={() => setH(true)} onMouseLeave={() => setH(false)}
      style={{ padding: '9px 14px', borderRadius: 999, cursor: 'pointer',
        border: `1px solid ${base.bd}`, background: base.bg, color: base.col,
        fontFamily: 'var(--font-body)', fontSize: 13.5, fontWeight: 540, lineHeight: 1.2,
        transition: 'all .16s ease', textAlign: 'left' }}>
      {children}
    </button>
  );
}

/* ---------- Fields ---------- */
export function FieldShell({ icon, label, children }: { icon: IconName; label: string; children: ReactNode }) {
  return (
    <label style={{ display: 'block' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8,
        fontFamily: 'var(--font-body)', fontSize: 12.5, fontWeight: 600, letterSpacing: '0.04em',
        textTransform: 'uppercase', color: 'var(--ink-soft)' }}>
        <Icon name={icon} size={15} stroke={1.7} color="var(--accent-strong)" />{label}
      </span>
      {children}
    </label>
  );
}

const inputStyle: CSSProperties = {
  width: '100%', boxSizing: 'border-box', fontFamily: 'var(--font-body)', fontSize: 15.5,
  color: 'var(--ink)', background: 'var(--input-bg)', border: '1px solid var(--hairline-strong)',
  borderRadius: 12, padding: '13px 14px', outline: 'none', resize: 'none', lineHeight: 1.5,
  transition: 'border-color .16s ease, box-shadow .16s ease',
};

interface TextFieldProps {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
  id?: string;
  ariaLabel?: string;
  disabled?: boolean;
}

export function TextArea({ value, onChange, placeholder, rows = 4, id, ariaLabel, disabled }: TextFieldProps) {
  const [f, setF] = useState(false);
  return (
    <textarea id={id} aria-label={ariaLabel} value={value} disabled={disabled}
      onChange={(e) => onChange(e.target.value)} placeholder={placeholder} rows={rows}
      onFocus={() => setF(true)} onBlur={() => setF(false)}
      style={{ ...inputStyle, borderColor: f ? 'var(--accent)' : 'var(--hairline-strong)',
        boxShadow: f ? '0 0 0 3px color-mix(in oklch, var(--accent) 16%, transparent)' : 'none' }} />
  );
}

export function TextInput({ value, onChange, placeholder, id, ariaLabel, disabled }: TextFieldProps) {
  const [f, setF] = useState(false);
  return (
    <input id={id} aria-label={ariaLabel} value={value} disabled={disabled}
      onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
      onFocus={() => setF(true)} onBlur={() => setF(false)}
      style={{ ...inputStyle, padding: '12px 13px', fontSize: 15,
        borderColor: f ? 'var(--accent)' : 'var(--hairline-strong)',
        boxShadow: f ? '0 0 0 3px color-mix(in oklch, var(--accent) 16%, transparent)' : 'none' }} />
  );
}

/* ---------- Confidence meter (qualitative — no invented %) ---------- */
export type ConfidenceLevel = 'confident' | 'likely' | 'uncertain';

const LEVEL_FILL: Record<ConfidenceLevel, number> = { confident: 92, likely: 64, uncertain: 36 };
const LEVEL_LABEL: Record<ConfidenceLevel, string> = { confident: 'Confident', likely: 'Likely', uncertain: 'Uncertain' };

export function ConfidenceMeter({ level }: { level: ConfidenceLevel }) {
  const [w, setW] = useState(0);
  const target = LEVEL_FILL[level];
  useEffect(() => { const t = setTimeout(() => setW(target), 120); return () => clearTimeout(t); }, [target]);
  const tone = level === 'uncertain' ? 'color-mix(in oklch, var(--ink) 30%, #b9b6ad)' : 'var(--accent)';
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 7, gap: 8 }}>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 11, fontWeight: 700, letterSpacing: '0.05em',
          textTransform: 'uppercase', color: 'var(--ink-soft)' }}>Confidence</span>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 13, fontWeight: 700, color: 'var(--ink)', whiteSpace: 'nowrap' }}>
          {LEVEL_LABEL[level]}</span>
      </div>
      <div style={{ height: 7, borderRadius: 999, background: 'var(--hairline-strong)', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${w}%`, borderRadius: 999, background: tone,
          transition: 'width .9s cubic-bezier(.2,.8,.2,1)' }} />
      </div>
    </div>
  );
}

/* ---------- Message scaffolding ---------- */
export function UserBubble({ children }: { children: ReactNode }) {
  return (
    <div className="msg-in" style={{ alignSelf: 'flex-end', maxWidth: '82%', padding: '11px 15px',
      borderRadius: '16px 16px 5px 16px', background: 'var(--accent)', color: 'var(--accent-ink)',
      fontFamily: 'var(--font-body)', fontSize: 14.5, lineHeight: 1.5,
      boxShadow: '0 4px 14px -8px var(--accent-shadow)' }}>{children}</div>
  );
}

export function AssistantRow({ children }: { children: ReactNode }) {
  return (
    <div className="msg-in" style={{ display: 'flex', gap: 10, alignSelf: 'stretch', maxWidth: '100%' }}>
      <span style={{ flex: 'none', marginTop: 1, display: 'grid', placeItems: 'center', width: 28, height: 28,
        borderRadius: 9, background: 'color-mix(in oklch, var(--accent) 14%, transparent)',
        color: 'var(--accent-strong)', border: '1px solid color-mix(in oklch, var(--accent) 22%, transparent)' }}>
        <Icon name="scope" size={15} stroke={1.7} />
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
    </div>
  );
}
