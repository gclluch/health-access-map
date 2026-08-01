import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import DetailPanel from './DetailPanel';
import { makeMetric, seedStore } from '../test/harness';

// The panel is where a flagged ZIP gets its explanation. The rankings merely hide those ZIPs
// (RankingsList.test.tsx); the map still lets you click one, and this is the only thing that
// tells you why its numbers look strange.
describe('DetailPanel caveats', () => {
  const show = (over: Parameters<typeof makeMetric>[0]) => {
    const m = makeMetric(over);
    seedStore([m], { selectedZcta: m.zcta5 });
    render(<DetailPanel />);
  };

  it('flags an institutional ZIP as a workplace, not a community', () => {
    show({ zcta5: '80045', institutional: true });

    expect(screen.getByText(/Institutional ZIP/).textContent).toContain('more registered providers than residents');
  });

  it('flags a small-population ZIP as low confidence', () => {
    show({ zcta5: '77555', low_confidence: true, population: 2 });

    expect(screen.getByText(/Low-confidence area/)).toBeTruthy();
  });

  it('says a 2-of-3 composite is the weaker estimate it is', () => {
    show({ zcta5: '90003', n_dims_scored: 2 });

    expect(screen.getByText(/Partial score/).textContent).toContain('2 of 3 dimensions');
  });

  it('shows no caveat at all for an ordinary residential ZIP', () => {
    show({ zcta5: '90001' });

    expect(screen.queryByText(/Institutional ZIP/)).toBeNull();
    expect(screen.queryByText(/Low-confidence area/)).toBeNull();
    expect(screen.queryByText(/Partial score/)).toBeNull();
  });

  it('renders nothing when no ZIP is selected', () => {
    seedStore([makeMetric({ zcta5: '90001' })], { selectedZcta: null });
    const { container } = render(<DetailPanel />);

    expect(container.textContent).toBe('');
  });
});
