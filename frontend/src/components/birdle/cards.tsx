/**
 * Birdle AI — result + inconclusive cards, adapted from the design to render
 * real backend data only (no invented field-marks / regional-note / % number).
 */
import { useState } from 'react';
import { Icon, ConfidenceMeter } from './primitives';
import { RichText } from './RichText';
import type { ResultCardData } from './types';
import type { SpeciesInfo } from '../../types/observation';

function AlternateRow({ species }: { species: SpeciesInfo }) {
  return (
    <div style={{ padding: '11px 13px', borderRadius: 11, border: '1px solid var(--hairline-strong)',
      background: 'var(--input-bg)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontFamily: 'var(--font-body)', fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>
          {species.common_name}</span>
        <a href={species.range_link} target="_blank" rel="noopener noreferrer"
          style={{ flex: 'none', display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600,
            color: 'var(--accent-strong)', textDecoration: 'none' }}>
          eBird<Icon name="arrow" size={13} /></a>
      </div>
      <div style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 13, color: 'var(--ink-soft)', marginTop: 2 }}>
        {species.scientific_name}</div>
      {species.reasoning && (
        <p style={{ margin: '6px 0 0', fontFamily: 'var(--font-body)', fontSize: 13, lineHeight: 1.45, color: 'var(--ink-soft)' }}>
          {species.reasoning}</p>
      )}
    </div>
  );
}

interface ResultCardProps {
  data: ResultCardData;
  noBanner?: boolean;
}

export function ResultCard({ data, noBanner }: ResultCardProps) {
  const [saved, setSaved] = useState(false);
  const [showAlts, setShowAlts] = useState(false);
  const [imgError, setImgError] = useState(false);
  const showPhoto = !!data.photo && !imgError;

  return (
    <div style={{ background: 'var(--card-bg)', border: 'var(--card-border)', borderRadius: 18,
      overflow: 'hidden', boxShadow: '0 14px 40px -26px rgba(18,22,16,0.5)' }}>
      {!noBanner && (
        <div style={{ position: 'relative', height: showPhoto ? 158 : 96, display: 'grid', placeItems: 'center',
          background: 'linear-gradient(135deg, color-mix(in oklch, var(--accent) 22%, var(--scrim)), var(--scrim))' }}>
          {showPhoto ? (
            <>
              <img src={data.photo} alt={data.name} onError={() => setImgError(true)}
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%',
                  objectFit: 'cover', objectPosition: '50% 35%' }} />
              <div style={{ position: 'absolute', inset: 0, background:
                'linear-gradient(180deg, rgba(0,0,0,0.22), transparent 38%, rgba(0,0,0,0.04) 64%, rgba(0,0,0,0.34))' }} />
            </>
          ) : (
            <Icon name="scope" size={30} stroke={1.5} color="rgba(255,255,255,0.55)" />
          )}
          <span style={{ position: 'absolute', top: 12, left: 12, padding: '5px 10px', borderRadius: 999,
            background: 'rgba(0,0,0,0.42)', backdropFilter: 'blur(6px)', color: '#fff',
            fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
            Best match
          </span>
        </div>
      )}

      <div style={{ padding: '16px 17px 17px', display: 'flex', flexDirection: 'column', gap: 15 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 'var(--display-weight)', fontSize: 25,
              lineHeight: 1.05, color: 'var(--ink)', letterSpacing: '-0.01em' }}>{data.name}</div>
            <div style={{ fontFamily: 'var(--font-display)', fontStyle: 'italic', fontSize: 14.5,
              color: 'var(--ink-soft)', marginTop: 3 }}>{data.sci}</div>
          </div>
          <button onClick={() => setSaved((s) => !s)} aria-label="Save"
            style={{ flex: 'none', display: 'grid', placeItems: 'center', width: 38, height: 38, borderRadius: 11,
              cursor: 'pointer', border: '1px solid var(--hairline-strong)',
              background: saved ? 'var(--accent)' : 'var(--input-bg)',
              color: saved ? 'var(--accent-ink)' : 'var(--ink-soft)', transition: 'all .18s' }}>
            <Icon name="bookmark" size={17} />
          </button>
        </div>

        <ConfidenceMeter level={data.level} />

        <RichText text={data.summary} style={{ fontSize: 14.5, lineHeight: 1.55 }} />

        {data.imageCredit && showPhoto && !noBanner && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, letterSpacing: '0.04em', color: 'var(--ink-faint)', marginTop: -8 }}>
            Photo · {data.imageCredit}
          </div>
        )}

        <a href={data.rangeLink} target="_blank" rel="noopener noreferrer"
          style={{ display: 'inline-flex', alignItems: 'center', alignSelf: 'flex-start', gap: 6, padding: '10px 15px',
            borderRadius: 12, textDecoration: 'none', fontFamily: 'var(--font-body)', fontSize: 13.5, fontWeight: 600,
            color: 'var(--accent-ink)', background: 'var(--accent)', boxShadow: '0 6px 18px -10px var(--accent-shadow)' }}>
          View on eBird<Icon name="arrow" size={15} />
        </a>

        {data.alternates.length > 0 && (
          <div>
            <button onClick={() => setShowAlts((s) => !s)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none',
                padding: '2px 0', cursor: 'pointer', fontFamily: 'var(--font-body)', fontSize: 11.5, fontWeight: 700,
                letterSpacing: '0.05em', textTransform: 'uppercase', color: 'var(--ink-soft)' }}>
              Could also be · {data.alternates.length}
              <Icon name="chevron" size={13} color="var(--ink-soft)"
                style={{ transform: showAlts ? 'rotate(90deg)' : 'none', transition: 'transform .2s' }} />
            </button>
            {showAlts && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 9 }}>
                {data.alternates.map((s, i) => <AlternateRow key={i} species={s} />)}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

interface InconclusiveCardProps {
  title: string;
  body: string;
}

export function InconclusiveCard({ title, body }: InconclusiveCardProps) {
  return (
    <div style={{ background: 'var(--card-bg)', border: 'var(--card-border)', borderRadius: 18,
      padding: '18px 17px', boxShadow: '0 14px 40px -28px rgba(18,22,16,0.45)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 11 }}>
        <span style={{ display: 'grid', placeItems: 'center', width: 34, height: 34, borderRadius: 10,
          background: 'color-mix(in oklch, var(--ink) 8%, transparent)', color: 'var(--ink-soft)' }}>
          <Icon name="search" size={18} />
        </span>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 'var(--display-weight)', fontSize: 20,
          color: 'var(--ink)' }}>{title}</div>
      </div>
      <RichText text={body} style={{ fontSize: 14.5, lineHeight: 1.55 }} />
    </div>
  );
}
