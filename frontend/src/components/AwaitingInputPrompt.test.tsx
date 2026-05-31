import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AwaitingInputPrompt } from './AwaitingInputPrompt';

describe('AwaitingInputPrompt', () => {
  it('renders the question', () => {
    render(
      <AwaitingInputPrompt question="Crest or no crest?" onAnswer={() => {}} />,
    );
    expect(screen.getByText('Crest or no crest?')).toBeInTheDocument();
  });

  it('renders a chip button per option and answers with its label', async () => {
    const onAnswer = vi.fn();
    render(
      <AwaitingInputPrompt
        question="Which one?"
        options={['Crest', 'No crest']}
        onAnswer={onAnswer}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: 'Crest' }));
    expect(onAnswer).toHaveBeenCalledWith('Crest');
  });

  it('answers with trimmed free text on submit', async () => {
    const onAnswer = vi.fn();
    render(<AwaitingInputPrompt question="Tell me more" onAnswer={onAnswer} />);

    await userEvent.type(
      screen.getByPlaceholderText(/type your answer/i),
      '  it was tiny  ',
    );
    await userEvent.click(screen.getByRole('button', { name: /send/i }));

    expect(onAnswer).toHaveBeenCalledWith('it was tiny');
  });

  it('does not answer on empty free-text submit', async () => {
    const onAnswer = vi.fn();
    render(<AwaitingInputPrompt question="Tell me more" onAnswer={onAnswer} />);

    // Send button is disabled while the field is empty.
    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
    expect(onAnswer).not.toHaveBeenCalled();
  });

  it('renders no chips when options is empty or omitted', () => {
    render(<AwaitingInputPrompt question="No options" onAnswer={() => {}} />);
    // Only the submit ("send") button should be present.
    expect(screen.getAllByRole('button')).toHaveLength(1);
  });

  it('disables interaction when disabled', () => {
    render(
      <AwaitingInputPrompt
        question="Busy"
        options={['A']}
        disabled
        onAnswer={() => {}}
      />,
    );
    expect(screen.getByRole('button', { name: 'A' })).toBeDisabled();
    expect(screen.getByPlaceholderText(/type your answer/i)).toBeDisabled();
  });
});
