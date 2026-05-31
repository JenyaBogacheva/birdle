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
    <div className="bg-blue-50 border-2 border-blue-300 rounded-lg p-5 shadow-sm space-y-4">
      <div className="flex items-start gap-3">
        <span className="text-2xl">🐦</span>
        <p className="text-base font-medium text-blue-900 leading-relaxed">
          {question}
        </p>
      </div>

      {options && options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {options.map((opt) => (
            <button
              key={opt}
              type="button"
              disabled={disabled}
              onClick={() => onAnswer(opt)}
              className="px-4 py-2 bg-white border border-blue-400 text-blue-700 text-sm font-medium rounded-full hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {opt}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="type your answer... ✍️"
          disabled={disabled}
          className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={disabled || !text.trim()}
          className="px-5 py-2 bg-blue-500 text-white text-sm font-medium rounded-lg hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          send 📨
        </button>
      </form>
    </div>
  );
}
