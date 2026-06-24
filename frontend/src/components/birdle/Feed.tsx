/**
 * Shared conversation-feed renderer for both the mobile and desktop layouts.
 */
import { useRef, useState } from 'react';
import { Icon, Chip, UserBubble, AssistantRow, PrimaryButton } from './primitives';
import { ThinkingBlock } from './Thinking';
import { ResultCard, InconclusiveCard } from './cards';
import { RichText } from './RichText';
import type { ClarifyItem, FeedItem } from './types';
import type { BirdleSession } from '../../hooks/useBirdleSession';

function ClarifyBlock({
  item, onAnswer, desktop,
}: { item: ClarifyItem; onAnswer: (msg: string) => void; desktop?: boolean }) {
  const [text, setText] = useState('');
  // Local latch: ignore further taps the instant one fires, before `answered`
  // round-trips through the resume turn (prevents a double-tap double-submit).
  const [submitted, setSubmitted] = useState(false);
  const answered = item.answered !== null || submitted;

  const send = (msg: string) => {
    if (answered) return;
    setSubmitted(true);
    onAnswer(msg);
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    send(t);
    setText('');
  };

  return (
    <>
      <RichText text={item.text} style={{ fontSize: desktop ? 15.5 : 14.5, lineHeight: 1.55, marginBottom: 12 }} />
      {item.options.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: desktop ? 9 : 8, marginBottom: answered ? 0 : 10 }}>
          {item.options.map((c, i) => (
            <Chip key={i} tone="accent" active={item.answered === c}
              onClick={() => send(c)}>{c}</Chip>
          ))}
        </div>
      )}
      {!answered && (
        <form onSubmit={submit} style={{ display: 'flex', gap: 8 }}>
          <input value={text} onChange={(e) => setText(e.target.value)} aria-label="Your answer"
            placeholder="Or type a reply…"
            style={{ flex: 1, minWidth: 0, fontFamily: 'var(--font-body)', fontSize: 14, color: 'var(--ink)',
              background: 'var(--input-bg)', border: '1px solid var(--hairline-strong)', borderRadius: 11,
              padding: '10px 13px', outline: 'none' }} />
          <button type="submit" aria-label="Send" disabled={!text.trim()}
            style={{ flex: 'none', display: 'grid', placeItems: 'center', width: 42, borderRadius: 11, border: 'none',
              cursor: text.trim() ? 'pointer' : 'default', background: text.trim() ? 'var(--accent)' : 'var(--hairline-strong)',
              color: 'var(--accent-ink)' }}>
            <Icon name="arrow" size={17} />
          </button>
        </form>
      )}
    </>
  );
}

/**
 * Structured actions shown after a turn concludes: quick decisions (confirm /
 * refine / ask / start over) plus a shared text composer. "Not quite" and "Ask
 * about it" just refocus the composer with a contextual prompt — the agent
 * decides each turn whether to re-identify or simply answer.
 */
export function ResultActions({ s, desktop }: { s: BirdleSession; desktop?: boolean }) {
  const last = s.feed[s.feed.length - 1];
  const isResult = last?.kind === 'result';
  const [confirmed, setConfirmed] = useState(false);
  const [mode, setMode] = useState<'chat' | 'refine'>('chat');
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const focusInput = () => setTimeout(() => inputRef.current?.focus(), 0);
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    s.followUp(t);
    setText('');
    setMode('chat');
  };

  const placeholder =
    mode === 'refine'
      ? 'What looked different? Add a detail…'
      : isResult
        ? 'Ask about this bird, or add a detail…'
        : 'Add a detail to narrow it down…';

  return (
    <div className={desktop ? 'bd-followup' : 'followup'}>
      {confirmed ? (
        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 10, marginBottom: 12 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontFamily: 'var(--font-body)',
            fontSize: 14, fontWeight: 600, color: 'var(--accent-strong)' }}>
            <Icon name="check" size={16} stroke={2.2} color="var(--accent-strong)" />Nice — glad we got it.
          </span>
          <Chip onClick={s.reset}>Identify another</Chip>
        </div>
      ) : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 11 }}>
          {isResult && <Chip tone="accent" solid onClick={() => setConfirmed(true)}>This is my bird</Chip>}
          <Chip onClick={() => { setMode('refine'); focusInput(); }}>Not quite</Chip>
          {isResult && <Chip onClick={() => { setMode('chat'); focusInput(); }}>Ask about it</Chip>}
          <Chip onClick={s.reset}>Identify another</Chip>
        </div>
      )}
      <form onSubmit={submit} style={{ display: 'flex', gap: 9, alignItems: 'center' }}>
        <input ref={inputRef} value={text} onChange={(e) => setText(e.target.value)} aria-label="Ask a follow-up"
          placeholder={placeholder}
          style={{ flex: 1, minWidth: 0, fontFamily: 'var(--font-body)', fontSize: desktop ? 15 : 14,
            color: 'var(--ink)', background: 'var(--input-bg)', border: '1px solid var(--hairline-strong)',
            borderRadius: 12, padding: desktop ? '13px 15px' : '12px 14px', outline: 'none' }} />
        <button type="submit" aria-label="Send follow-up" disabled={!text.trim()}
          style={{ flex: 'none', display: 'grid', placeItems: 'center', width: 46, height: 46, borderRadius: 12,
            border: 'none', cursor: text.trim() ? 'pointer' : 'default',
            background: text.trim() ? 'var(--accent)' : 'var(--hairline-strong)', color: 'var(--accent-ink)' }}>
          <Icon name="arrow" size={18} />
        </button>
      </form>
    </div>
  );
}

interface FeedItemsProps {
  feed: FeedItem[];
  onAnswer: (msg: string) => void;
  onRetry: () => void;
  desktop?: boolean;
}

export function FeedItems({ feed, onAnswer, onRetry, desktop }: FeedItemsProps) {
  return (
    <>
      {feed.map((item) => {
        switch (item.kind) {
          case 'user':
            return <UserBubble key={item.id}>{item.text}</UserBubble>;
          case 'thinking':
            if (!item.active && item.steps.length === 0) return null;
            return <AssistantRow key={item.id}><ThinkingBlock item={item} /></AssistantRow>;
          case 'clarify':
            return (
              <AssistantRow key={item.id}>
                <ClarifyBlock item={item} onAnswer={onAnswer} desktop={desktop} />
              </AssistantRow>
            );
          case 'answer':
            return (
              <AssistantRow key={item.id}>
                <RichText text={item.text} style={{ fontSize: desktop ? 15.5 : 14.5, lineHeight: 1.55 }} />
              </AssistantRow>
            );
          case 'result':
            return <AssistantRow key={item.id}><ResultCard data={item.data} noBanner={desktop} /></AssistantRow>;
          case 'inconclusive':
            return (
              <AssistantRow key={item.id}>
                <InconclusiveCard title={item.title} body={item.body} clarification={item.clarification} />
              </AssistantRow>
            );
          case 'error':
            return (
              <AssistantRow key={item.id}>
                <div style={{ background: 'color-mix(in oklch, #b4452f 12%, var(--card-bg))',
                  border: '1px solid color-mix(in oklch, #b4452f 30%, transparent)', borderRadius: 14, padding: '14px 15px' }}>
                  <div style={{ display: 'flex', gap: 9, alignItems: 'flex-start' }}>
                    <Icon name="info" size={18} color="#b4452f" style={{ flex: 'none', marginTop: 1 }} />
                    <p style={{ margin: 0, fontFamily: 'var(--font-body)', fontSize: 14, lineHeight: 1.5, color: 'var(--ink)' }}>
                      {item.text}</p>
                  </div>
                  {item.canRetry && (
                    <div style={{ marginTop: 12 }}>
                      <PrimaryButton icon="arrow" onClick={onRetry}>Try again</PrimaryButton>
                    </div>
                  )}
                </div>
              </AssistantRow>
            );
          default:
            return null;
        }
      })}
    </>
  );
}
