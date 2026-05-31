// frontend/src/pages/BirdleApp.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BirdleApp from './BirdleApp';
import type { StreamEvent } from '../types/observation';

vi.mock('../api/client', () => ({
  identifyBirdStream: vi.fn(),
  resumeIdentificationStream: vi.fn(),
}));

import { identifyBirdStream, resumeIdentificationStream } from '../api/client';

const submitObservation = async () => {
  const user = userEvent.setup();
  // BirdForm placeholder: "A small bird with bright blue feathers..."
  await user.type(
    screen.getByPlaceholderText('A small bird with bright blue feathers...'),
    'a small blue bird',
  );
  // BirdForm location placeholder: "Central Park, NY"
  await user.type(
    screen.getByPlaceholderText('Central Park, NY'),
    'Central Park, NY',
  );
  await user.click(screen.getByRole('button', { name: /investigate/i }));
  return user;
};

describe('BirdleApp HITL', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the clarifying prompt on awaiting_input and resumes on answer', async () => {
    (identifyBirdStream as ReturnType<typeof vi.fn>).mockImplementation(
      async (_obs: unknown, onEvent: (e: StreamEvent) => void) => {
        onEvent({ type: 'session_id', session_id: 'sess-123' });
        onEvent({
          type: 'awaiting_input',
          reason: 'disambiguate',
          question: 'Did it have a crest?',
          options: ['Yes', 'No'],
        });
        onEvent({ type: 'done' });
      },
    );
    (resumeIdentificationStream as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);

    render(<BirdleApp />);
    const user = await submitObservation();

    await waitFor(() =>
      expect(screen.getByText('Did it have a crest?')).toBeInTheDocument(),
    );

    await user.click(screen.getByRole('button', { name: 'Yes' }));
    await waitFor(() =>
      expect(resumeIdentificationStream).toHaveBeenCalledWith(
        { session_id: 'sess-123', user_message: 'Yes' },
        expect.any(Function),
        expect.any(AbortSignal),
      ),
    );
  });

  it('clears the prompt after the resumed stream returns a result', async () => {
    (identifyBirdStream as ReturnType<typeof vi.fn>).mockImplementation(
      async (_obs: unknown, onEvent: (e: StreamEvent) => void) => {
        onEvent({ type: 'session_id', session_id: 's-42' });
        onEvent({
          type: 'awaiting_input',
          reason: 'disambiguate',
          question: 'Crest?',
          options: ['Yes'],
        });
        onEvent({ type: 'done' });
      },
    );
    (resumeIdentificationStream as ReturnType<typeof vi.fn>).mockImplementation(
      async (_payload: unknown, onEvent: (e: StreamEvent) => void) => {
        onEvent({
          type: 'result',
          data: { message: 'Northern Cardinal', alternate_species: [] },
        });
        onEvent({ type: 'done' });
      },
    );

    render(<BirdleApp />);
    const user = await submitObservation();

    await waitFor(() => expect(screen.getByText('Crest?')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: 'Yes' }));
    await waitFor(() =>
      expect(screen.queryByText('Crest?')).not.toBeInTheDocument(),
    );
  });

  it('shows an error and does not resume if answered after the session was lost', async () => {
    (identifyBirdStream as ReturnType<typeof vi.fn>).mockImplementation(
      async (_obs: unknown, onEvent: (e: StreamEvent) => void) => {
        // No session_id event emitted — the session is "lost".
        onEvent({
          type: 'awaiting_input',
          reason: 'clarify',
          question: 'Where exactly?',
          options: ['Skip'],
        });
        onEvent({ type: 'done' });
      },
    );

    render(<BirdleApp />);
    const user = await submitObservation();

    await waitFor(() =>
      expect(screen.getByText('Where exactly?')).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: 'Skip' }));

    await waitFor(() =>
      expect(screen.getByText(/start a new identification/i)).toBeInTheDocument(),
    );
    expect(resumeIdentificationStream).not.toHaveBeenCalled();
  });
});
