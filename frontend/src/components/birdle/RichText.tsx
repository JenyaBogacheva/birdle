/**
 * Markdown renderer for the agent's prose (clarifying questions, summaries).
 * Uses react-markdown with element overrides so block spacing and type match
 * the rest of the UI. `style` sets the inherited font size / colour / leading.
 */
import ReactMarkdown, { type Components } from 'react-markdown';
import type { CSSProperties } from 'react';

// On-brand: a small set of calm nature/bird glyphs may pass through; every
// other emoji/pictograph (the agent's coloured-circle bullets, ✅/⚠️ signs,
// etc.) is stripped so the prose stays nature-led regardless of model output.
const NATURE_EMOJI = new Set(['🐦', '🪶', '🌿', '🌱', '🍃', '🌳', '🦅', '🦉', '🕊️', '🐤', '🐣', '🌾']);
// Match emoji sequences (with optional ZWJ joins and variation selector).
const EMOJI_SEQ = /\p{Extended_Pictographic}(‍\p{Extended_Pictographic})*️?/gu;

/**
 * Tidy the agent's prose for Markdown rendering: strip off-brand emoji, insert
 * a break before any inline numbered-list marker ("1. … 2. …") so it renders as
 * a real list (an ordered list starting at 1 may interrupt a paragraph per
 * CommonMark), and collapse the whitespace emoji removal leaves behind.
 */
function normalize(text: string): string {
  return text
    .replace(EMOJI_SEQ, (m) =>
      NATURE_EMOJI.has(m) || NATURE_EMOJI.has(m.replace(/️/g, '')) ? m : '',
    )
    .replace(/([^\n])[ \t]+(\d+\.\s)/g, '$1\n$2')
    .replace(/[ \t]{2,}/g, ' ');
}

const components: Components = {
  p: ({ children }) => <p style={{ margin: 0 }}>{children}</p>,
  ul: ({ children }) => <ul style={{ margin: 0, paddingLeft: '1.25em', display: 'flex', flexDirection: 'column', gap: 4 }}>{children}</ul>,
  ol: ({ children }) => <ol style={{ margin: 0, paddingLeft: '1.35em', display: 'flex', flexDirection: 'column', gap: 4 }}>{children}</ol>,
  li: ({ children }) => <li style={{ margin: 0, lineHeight: 1.5 }}>{children}</li>,
  strong: ({ children }) => <strong style={{ fontWeight: 700 }}>{children}</strong>,
  em: ({ children }) => <em>{children}</em>,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer"
      style={{ color: 'var(--accent-strong)', textDecoration: 'underline' }}>{children}</a>
  ),
  code: ({ children }) => (
    <code style={{ fontFamily: 'var(--font-mono)', fontSize: '0.92em',
      background: 'color-mix(in oklch, var(--ink) 8%, transparent)', padding: '1px 5px', borderRadius: 5 }}>
      {children}</code>
  ),
};

export function RichText({ text, style }: { text: string; style?: CSSProperties }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8,
      fontFamily: 'var(--font-body)', color: 'var(--ink)', ...style }}>
      <ReactMarkdown components={components}>{normalize(text)}</ReactMarkdown>
    </div>
  );
}
