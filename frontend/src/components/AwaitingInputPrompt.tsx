/**
 * Prompt shown when the agent pauses to ask the user a question
 * (the `awaiting_input` SSE event). Offers quick-reply chips and a
 * free-text field; both resume the conversation via onAnswer.
 */
import { useState } from 'react';

interface AwaitingInputPromptProps {
  question: string;
  options?: string[];
  disabled?: boolean;
  onAnswer: (message: string) => void;
}

export function AwaitingInputPrompt({
  question,
  options,
  disabled = false,
  onAnswer,
}: AwaitingInputPromptProps) {
  const [text, setText] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed) return;
    onAnswer(trimmed);
    setText('');
  };

  return (
    <div className="glass rounded-xl p-5 space-y-4 animate-fade-in">
      <p className="font-hand text-secondary text-xl leading-relaxed">
        {question}
      </p>

      {options && options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {options.map((opt, i) => (
            <button
              key={`${opt}-${i}`}
              type="button"
              disabled={disabled}
              onClick={() => onAnswer(opt)}
              className="px-4 py-2 rounded-full border border-dashed border-white/30 font-hand text-secondary hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-white/40 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          aria-label="Your answer"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="type your answer... ✍️"
          disabled={disabled}
          className="flex-1 bg-white/5 border border-dashed border-white/20 rounded-lg px-4 py-2 text-primary placeholder-white/30 focus:outline-none focus:border-white/40 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={disabled || !text.trim()}
          className="glass rounded-lg px-5 py-2 font-hand text-primary hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          send 📨
        </button>
      </form>
    </div>
  );
}
