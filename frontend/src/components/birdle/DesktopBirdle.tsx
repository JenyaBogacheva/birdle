/**
 * Birdle AI — desktop layout: a full-bleed photo poster beside a frosted
 * working column. Ported from the design's app/birdle-desktop.jsx.
 */
import {
  Icon, Brand, PrimaryButton, FieldShell, TextArea, TextInput, LocateButton,
} from './primitives';
import { FeedItems, ResultActions } from './Feed';
import { useFeedScroll } from '../../hooks/useFeedScroll';
import type { BirdleSession } from '../../hooks/useBirdleSession';
import type { ResultCardData } from './types';

function DeskCompose({ s }: { s: BirdleSession }) {
  return (
    <div className="bd-compose">
      <div className="bd-compose-inner">
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: '0.18em',
          textTransform: 'uppercase', color: 'var(--accent-strong)', marginBottom: 14 }}>
          Describe to identify
        </div>
        <h1 style={{ fontFamily: 'var(--font-display)', fontWeight: 'var(--display-weight)', fontSize: 44,
          lineHeight: 1.04, letterSpacing: '-0.02em', color: 'var(--ink)', margin: '0 0 12px' }}>
          What did you see?
        </h1>
        <p style={{ margin: '0 0 28px', fontFamily: 'var(--font-body)', fontSize: 16.5, lineHeight: 1.55,
          color: 'var(--ink-soft)', maxWidth: 500 }}>
          Describe the bird in your own words — size, colours, markings, the way it moved. Birdle
          weighs the details against what’s around you.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
          <TextArea value={s.desc} onChange={s.setDesc} rows={5} ariaLabel="What did you see?"
            placeholder="Small, with a flash of blue and a loud call…" />

          <div style={{ display: 'flex', gap: 16 }}>
            <div style={{ flex: 1 }}>
              <FieldShell icon="pin" label="Where">
                <TextInput value={s.loc} onChange={s.setLoc} ariaLabel="Where" placeholder="City or area"
                  trailing={<LocateButton status={s.geoStatus}
                    onClick={s.geoStatus === 'on' ? s.clearCoords : s.useMyLocation} />} />
                {s.geoStatus === 'error' && (
                  <span className="bd-geo-hint">Couldn’t find your location — type it instead.</span>
                )}
              </FieldShell>
            </div>
            <div style={{ flex: 1 }}>
              <FieldShell icon="clock" label="When · optional">
                <TextInput value={s.time} onChange={s.setTime} ariaLabel="When" placeholder="e.g. this morning" />
              </FieldShell>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-start', marginTop: 4 }}>
            <PrimaryButton icon="arrow" disabled={!s.canStart} onClick={s.start}>Identify this bird</PrimaryButton>
          </div>
        </div>
      </div>
    </div>
  );
}

function DeskConversation({ s }: { s: BirdleSession }) {
  const scroller = useFeedScroll(s.feed);
  return (
    <div className="bd-conv">
      <header className="bd-conv-head">
        <button onClick={s.reset} aria-label="Start over"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 8, height: 40, padding: '0 14px',
            borderRadius: 11, cursor: 'pointer', border: '1px solid var(--hairline-strong)',
            background: 'var(--input-bg)', color: 'var(--ink)', fontFamily: 'var(--font-body)',
            fontSize: 13.5, fontWeight: 600 }}>
          <Icon name="back" size={17} />New
        </button>
        {(s.loc || s.time) && (
          <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 7, padding: '8px 14px',
            borderRadius: 999, background: 'var(--input-bg)', border: '1px solid var(--hairline-strong)',
            fontFamily: 'var(--font-body)', fontSize: 13, color: 'var(--ink-soft)' }}>
            <Icon name="pin" size={14} color="var(--accent-strong)" />
            <span>{s.loc}{s.time ? ` · ${s.time}` : ''}</span>
          </span>
        )}
      </header>

      <div className="bd-feed" ref={scroller}>
        <div className="bd-feed-inner">
          <FeedItems feed={s.feed} onAnswer={s.answer} onRetry={s.retry} desktop />
        </div>
      </div>
      {s.canFollowUp && <ResultActions s={s} desktop />}
    </div>
  );
}

function DeskPoster({ s }: { s: BirdleSession }) {
  const result: ResultCardData | null = s.result;
  const thinking = s.phase === 'conversation' && !result;
  const photoUrl = (s.vars as Record<string, string>)['--photo-url'];
  return (
    <div className={'bd-poster' + (thinking ? ' is-thinking' : '')}>
      <div className="bd-poster-photo" style={{ backgroundImage: photoUrl }} />
      <div className="bd-poster-tint" />
      <div className="bd-poster-scrim" />
      <div className="bd-poster-veil" />

      <div className="bd-poster-top">
        <Brand light />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.16em',
          textTransform: 'uppercase', color: 'rgba(255,255,255,0.82)' }}>field guide</span>
      </div>

      <div className="bd-poster-bot">
        {result ? (
          <div className="bd-hero" key="hero">
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, marginBottom: 16,
              padding: '6px 12px', borderRadius: 999, background: 'rgba(0,0,0,0.34)',
              backdropFilter: 'blur(8px)', border: '1px solid rgba(255,255,255,0.22)' }}>
              <Icon name="check" size={14} stroke={2.2} color="#fff" />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, letterSpacing: '0.1em',
                textTransform: 'uppercase', color: '#fff', whiteSpace: 'nowrap' }}>Best match</span>
            </div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 'var(--display-weight)', fontSize: 56,
              lineHeight: 1.0, letterSpacing: '-0.02em', color: '#fff', textShadow: '0 2px 24px rgba(0,0,0,0.5)' }}>
              {result.name}</div>
            <div style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 22,
              color: 'rgba(255,255,255,0.9)', marginTop: 8, textShadow: '0 1px 16px rgba(0,0,0,0.5)' }}>
              {result.sci}</div>
          </div>
        ) : thinking ? (
          <div key="status" style={{ display: 'inline-flex', alignItems: 'center', gap: 10,
            padding: '9px 15px', borderRadius: 999, background: 'rgba(0,0,0,0.32)', backdropFilter: 'blur(8px)',
            border: '1px solid rgba(255,255,255,0.2)' }}>
            <span className="pulse-dot" style={{ background: '#fff' }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: '0.06em', color: '#fff' }}>
              Identifying{s.loc ? ` near ${s.loc}` : ''}…</span>
          </div>
        ) : (
          <div key="tag">
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 'var(--display-weight)', fontSize: 40,
              lineHeight: 1.08, letterSpacing: '-0.02em', color: '#fff',
              textShadow: '0 2px 22px rgba(0,0,0,0.45)', maxWidth: 380 }}>
              Put a name to what you saw.</div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, letterSpacing: '0.1em',
              textTransform: 'uppercase', color: 'rgba(255,255,255,0.78)', marginTop: 16 }}>
              Description in · species out</div>
          </div>
        )}
      </div>
    </div>
  );
}

export function DesktopBirdle({ s }: { s: BirdleSession }) {
  return (
    <div className="bd-desk" style={s.vars}>
      <DeskPoster s={s} />
      <div className="bd-work">
        {s.phase === 'compose' ? <DeskCompose s={s} /> : <DeskConversation s={s} />}
      </div>
    </div>
  );
}
