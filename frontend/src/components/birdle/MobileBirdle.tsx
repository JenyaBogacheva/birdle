/**
 * Birdle AI — mobile layout: full-bleed photo under a frosted sheet (compose)
 * that flips into a conversation feed. Ported from the design's app/birdle.jsx.
 */
import {
  Icon, Brand, PrimaryButton, FieldShell, TextArea, TextInput,
} from './primitives';
import { FeedItems, ResultActions } from './Feed';
import { useFeedScroll } from '../../hooks/useFeedScroll';
import type { BirdleSession } from '../../hooks/useBirdleSession';

function ComposeView({ s }: { s: BirdleSession }) {
  return (
    <div className="compose-wrap">
      <div className="compose-top">
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, padding: '16px 24px',
          paddingTop: 'calc(16px + env(safe-area-inset-top))',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Brand light />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.1em',
            textTransform: 'uppercase', color: 'rgba(255,255,255,0.78)' }}>field guide</span>
        </div>
      </div>

      <div className="sheet" style={{ borderRadius: '26px 26px 0 0', padding: '12px 24px 22px' }}>
        <div className="grabber" />
        <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 'var(--display-weight)', fontSize: 27,
          lineHeight: 1.08, letterSpacing: '-0.015em', color: 'var(--ink)', margin: '4px 0 6px' }}>
          What did you see?</h1>
        <p style={{ margin: '0 0 16px', fontFamily: 'var(--font-body)', fontSize: 14.5, lineHeight: 1.5, color: 'var(--ink-soft)' }}>
          Describe the bird in your own words — size, colours, markings, the way it moved.</p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <TextArea value={s.desc} onChange={s.setDesc} rows={4} ariaLabel="What did you see?"
            placeholder="Small, with a flash of blue and a loud call…" />

          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <FieldShell icon="pin" label="Where">
                <TextInput value={s.loc} onChange={s.setLoc} ariaLabel="Where" placeholder="City or area" />
              </FieldShell>
            </div>
            <div style={{ flex: 1 }}>
              <FieldShell icon="clock" label="When · optional">
                <TextInput value={s.time} onChange={s.setTime} ariaLabel="When" placeholder="e.g. this morning" />
              </FieldShell>
            </div>
          </div>

          <PrimaryButton full icon="arrow" disabled={!s.canStart} onClick={s.start}>Identify this bird</PrimaryButton>
        </div>
      </div>
    </div>
  );
}

function ConversationView({ s }: { s: BirdleSession }) {
  const scroller = useFeedScroll(s.feed);
  return (
    <div className="conv-wrap">
      <header className="conv-head">
        <button onClick={s.reset} aria-label="Back" style={{ display: 'grid', placeItems: 'center', width: 36, height: 36,
          borderRadius: 10, cursor: 'pointer', border: '1px solid var(--hairline-strong)', background: 'var(--input-bg)',
          color: 'var(--ink)' }}>
          <Icon name="back" size={18} />
        </button>
        <Brand />
        {(s.loc || s.time) && (
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 11px',
            borderRadius: 999, background: 'var(--input-bg)', border: '1px solid var(--hairline-strong)',
            fontFamily: 'var(--font-body)', fontSize: 12, color: 'var(--ink-soft)', maxWidth: 150, overflow: 'hidden' }}>
            <Icon name="pin" size={13} color="var(--accent-strong)" />
            <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {s.loc}{s.time ? ` · ${s.time}` : ''}</span>
          </span>
        )}
      </header>

      <div className="feed" ref={scroller}>
        <FeedItems feed={s.feed} onAnswer={s.answer} onRetry={s.retry} />
      </div>
      {s.canFollowUp && <ResultActions s={s} />}
    </div>
  );
}

export function MobileBirdle({ s }: { s: BirdleSession }) {
  return (
    <div className="birdle-screen" style={s.vars}>
      <div className={'bg-layer' + (s.phase === 'conversation' ? ' bg-dim' : '')}>
        <div className="bg-photo" style={{ backgroundImage: (s.vars as Record<string, string>)['--photo-url'] }} />
        <div className="bg-tint" />
        <div className="bg-scrim" />
        <div className="bg-veil" />
      </div>
      {s.phase === 'compose' ? <ComposeView s={s} /> : <ConversationView s={s} />}
    </div>
  );
}
