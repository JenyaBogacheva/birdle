/**
 * Live "thinking" block. Unlike the design's scripted ThinkingStream, this is
 * driven by real backend status/tool events: `steps` grows over time and the
 * block collapses to a summary once the turn produces a terminal event.
 */
import { useState } from 'react';
import { Icon } from './primitives';
import type { ThinkingItem } from './types';

function ThinkingSummary({ count, onToggle, open }: { count: number; onToggle: () => void; open: boolean }) {
  return (
    <button onClick={onToggle} style={{ display: 'inline-flex', alignItems: 'center', gap: 7,
      background: 'none', border: 'none', padding: '2px 0', cursor: 'pointer',
      fontFamily: 'var(--font-mono)', fontSize: 11.5, letterSpacing: '0.04em', color: 'var(--ink-faint)' }}>
      <Icon name="check" size={13} stroke={2} color="var(--accent-strong)" />
      Weighed {count} {count === 1 ? 'signal' : 'signals'}
      <Icon name="chevron" size={13} color="var(--ink-faint)"
        style={{ transform: open ? 'rotate(90deg)' : 'none', transition: 'transform .2s' }} />
    </button>
  );
}

export function ThinkingBlock({ item }: { item: ThinkingItem }) {
  const [open, setOpen] = useState(false);
  const steps = item.steps;

  // Nothing worth showing if the turn ended before any signal arrived
  // (e.g. the connection failed immediately).
  if (!item.active && steps.length === 0) return null;

  if (!item.active) {
    return (
      <div>
        <ThinkingSummary count={steps.length} open={open} onToggle={() => setOpen((o) => !o)} />
        {open && (
          <div style={{ marginTop: 8, paddingLeft: 12, borderLeft: '2px solid var(--hairline-strong)',
            display: 'flex', flexDirection: 'column', gap: 5 }}>
            {steps.map((s, i) => (
              <span key={i} style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-faint)', lineHeight: 1.5 }}>{s}</span>
            ))}
          </div>
        )}
      </div>
    );
  }

  const last = steps.length - 1;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 9, padding: '2px 2px 4px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span className="pulse-dot" />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, letterSpacing: '0.06em',
          textTransform: 'uppercase', color: 'var(--accent-strong)' }}>Thinking</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {steps.map((s, i) => (
          <div key={i} className="think-line" style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
            <span style={{ marginTop: 6, width: 4, height: 4, borderRadius: 999, flex: 'none',
              background: i === last ? 'var(--accent)' : 'var(--ink-faint)' }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12.5, lineHeight: 1.5,
              color: i === last ? 'var(--ink-soft)' : 'var(--ink-faint)' }}>{s}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
