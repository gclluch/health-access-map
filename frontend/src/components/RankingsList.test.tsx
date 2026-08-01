import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import RankingsList from './RankingsList';
import { useStore } from '../store';
import { makeMetric, seedStore } from '../test/harness';

// The headline ranking is the one place a flagged ZIP would be presented as a peer of real
// communities, so the exclusions (audit A2) are the behaviour worth locking, not the markup.
describe('RankingsList', () => {
  const ordinary = makeMetric({ zcta5: '90001', access_gap_score: 90, city: 'Ordinary' });

  it('keeps flagged and unscoreable ZIPs out of the headline list', () => {
    seedStore([
      ordinary,
      makeMetric({ zcta5: '80045', access_gap_score: 99, city: 'Campus', institutional: true }),
      makeMetric({ zcta5: '77555', access_gap_score: 98, city: 'Tiny', low_confidence: true }),
      makeMetric({ zcta5: '00001', access_gap_score: 97, city: 'Unscored', scoreable: false }),
    ]);
    render(<RankingsList />);

    const rows = screen.getAllByTestId('ranking-row');
    expect(rows).toHaveLength(1);
    expect(rows[0].textContent).toContain('Ordinary');
  });

  it('drops 2-of-3 partial scores on a composite lens but keeps full ones', () => {
    seedStore([ordinary, makeMetric({ zcta5: '90002', city: 'Partial', n_dims_scored: 2 })]);
    render(<RankingsList />);

    expect(screen.getAllByTestId('ranking-row')).toHaveLength(1);
    expect(screen.queryByText(/Partial/)).toBeNull();
  });

  it('honours the state filter', () => {
    seedStore(
      [ordinary, makeMetric({ zcta5: '10001', city: 'Elsewhere', state: 'NY' })],
      { stateFilter: 'NY' },
    );
    render(<RankingsList />);

    const rows = screen.getAllByTestId('ranking-row');
    expect(rows).toHaveLength(1);
    expect(rows[0].textContent).toContain('Elsewhere');
  });

  it('reverses the order when the direction toggle flips to lowest-first', () => {
    // The composite lens recomputes from the dimension percentiles under the live weights, so the
    // ordering has to be driven from those - access_gap_score itself is never read here.
    seedStore([
      makeMetric({
        zcta5: '90001', city: 'Worst',
        health_need_pctile: 90, social_vulnerability_pctile: 90, care_access_pctile: 90,
      }),
      makeMetric({
        zcta5: '90002', city: 'Best',
        health_need_pctile: 10, social_vulnerability_pctile: 10, care_access_pctile: 10,
      }),
    ]);
    render(<RankingsList />);
    expect(screen.getAllByTestId('ranking-row')[0].textContent).toContain('Worst');

    fireEvent.click(screen.getByRole('button', { name: 'Lowest' }));

    expect(useStore.getState().rankOrder).toBe('asc');
    expect(screen.getAllByTestId('ranking-row')[0].textContent).toContain('Best');
  });

  it('selects the ZIP a row click names', () => {
    seedStore([ordinary]);
    render(<RankingsList />);

    fireEvent.click(screen.getByTestId('ranking-row'));

    expect(useStore.getState().selectedZcta).toBe('90001');
  });

  it('says so rather than rendering an empty list when nothing qualifies', () => {
    seedStore([makeMetric({ zcta5: '90001', scoreable: false })]);
    render(<RankingsList />);

    expect(screen.getByText(/No ranked ZIPs/)).toBeTruthy();
    expect(screen.queryAllByTestId('ranking-row')).toHaveLength(0);
  });
});
