import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import CompareTray from './CompareTray';
import { makeMetric, seedStore } from '../test/harness';

// The static deploy has no backend, so the enriched columns are best-effort by design. What must
// not happen is a silent gap: the dimension rows come from the in-memory metrics either way, and
// a failed enrichment has to say so.
describe('CompareTray', () => {
  const two = [
    makeMetric({ zcta5: '90001', city: 'Alpha' }),
    makeMetric({ zcta5: '90002', city: 'Beta' }),
  ];

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503 })));
  });

  it('renders nothing until there is something to compare', () => {
    seedStore(two, { compareZctas: [] });
    const { container } = render(<CompareTray />);

    expect(container.textContent).toBe('');
  });

  it('renders the dimension rows from the slim metrics with no backend', async () => {
    seedStore(two, { compareZctas: ['90001', '90002'] });
    render(<CompareTray />);

    expect(await screen.findByText('Alpha')).toBeTruthy();
    expect(screen.getByText('Beta')).toBeTruthy();
    expect(screen.getByText('Health need')).toBeTruthy();
    expect(screen.getByText('Barriers to care')).toBeTruthy();
  });

  it('says the enriched measures are unavailable rather than hiding the gap', async () => {
    seedStore(two, { compareZctas: ['90001', '90002'] });
    render(<CompareTray />);

    await waitFor(() =>
      expect(screen.getByRole('status').textContent).toContain('Detailed measures are unavailable'));
  });
});
