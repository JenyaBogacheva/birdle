import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Home } from './Home';
import type { StreamEvent } from '../types/observation';

vi.mock('../api/client', () => ({
  identifyBird: vi.fn(),
  identifyBirdStream: vi.fn(),
  resumeIdentificationStream: vi.fn(),
}));

import {
  identifyBirdStream,
  resumeIdentificationStream,
} from '../api/client';

async function fillAndSubmit() {
  await userEvent.type(
    screen.getByLabelText(/what did you see/i),
    'small red bird with a crest',
  );
  await userEvent.type(screen.getByLabelText(/where are you/i), 'New York');
  await userEvent.click(screen.getByRole('button', { name: /let's go/i }));
}

describe('Home — HITL resume flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the awaiting prompt when the stream pauses', async () => {
    vi.mocked(identifyBirdStream).mockImplementation(
      async (_observation, onEvent: (e: StreamEvent) => void) => {
        onEvent({ type: 'session_id', session_id: 's-1' });
        onEvent({
          type: 'awaiting_input',
          reason: 'disambiguate_species',
          question: 'Crest or no crest?',
          options: ['Crest', 'No crest'],
        });
      },
    );

    render(<Home />);
    await fillAndSubmit();

    expect(await screen.findByText('Crest or no crest?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Crest' })).toBeInTheDocument();
  });

  it('resumes with the captured session_id when a chip is clicked', async () => {
    vi.mocked(identifyBirdStream).mockImplementation(
      async (_observation, onEvent: (e: StreamEvent) => void) => {
        onEvent({ type: 'session_id', session_id: 's-42' });
        onEvent({
          type: 'awaiting_input',
          reason: 'disambiguate_species',
          question: 'Crest or no crest?',
          options: ['Crest'],
        });
      },
    );
    vi.mocked(resumeIdentificationStream).mockImplementation(
      async (_payload, onEvent: (e: StreamEvent) => void) => {
        onEvent({
          type: 'result',
          data: {
            message: 'It is a Northern Cardinal.',
            alternate_species: [],
          },
        });
      },
    );

    render(<Home />);
    await fillAndSubmit();
    await screen.findByText('Crest or no crest?');

    await userEvent.click(screen.getByRole('button', { name: 'Crest' }));

    expect(resumeIdentificationStream).toHaveBeenCalledWith(
      { session_id: 's-42', user_message: 'Crest' },
      expect.any(Function),
      expect.any(Object),
    );
    expect(
      await screen.findByText('It is a Northern Cardinal.'),
    ).toBeInTheDocument();
  });

  it('shows an error if answered after the session was lost', async () => {
    // Stream pauses but never emits a session_id.
    vi.mocked(identifyBirdStream).mockImplementation(
      async (_observation, onEvent: (e: StreamEvent) => void) => {
        onEvent({
          type: 'awaiting_input',
          reason: 'clarify_location',
          question: 'Where did you see it?',
          options: ['Skip — no location'],
        });
      },
    );

    render(<Home />);
    await fillAndSubmit();
    await screen.findByText('Where did you see it?');

    await userEvent.click(
      screen.getByRole('button', { name: 'Skip — no location' }),
    );

    expect(
      await screen.findByText(/start a new identification/i),
    ).toBeInTheDocument();
    expect(resumeIdentificationStream).not.toHaveBeenCalled();
  });
});
