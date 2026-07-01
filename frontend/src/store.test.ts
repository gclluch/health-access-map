import { describe, it, expect, vi, afterEach } from 'vitest';
import { useStore } from './store';
import { SUBSCORE_LAZY_COLS, type SlimMetric } from './lib/types';

// T8: sub-score lens columns (subscores.json) load lazily on first sub-score metric select and are
// merged onto the already-loaded SlimMetric records. Assert the merge + one-time-fetch caching.
describe('ensureSubscoreColumns (T8 lazy sub-score merge)', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('fetches subscores.json once and merges its columns onto the records', async () => {
    const subs: Record<string, unknown> = { n: 2, zcta5: ['00001', '00002'] };
    for (const c of SUBSCORE_LAZY_COLS) subs[c] = [11, 22];
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => subs }));
    vi.stubGlobal('fetch', fetchMock);

    useStore.setState({
      metrics: new Map([
        ['00001', { zcta5: '00001' } as unknown as SlimMetric],
        ['00002', { zcta5: '00002' } as unknown as SlimMetric],
      ]),
      subscoresStatus: 'idle',
    });

    await useStore.getState().ensureSubscoreColumns();
    await useStore.getState().ensureSubscoreColumns(); // second call reuses the cached promise

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith('/subscores.json');
    expect(useStore.getState().subscoresStatus).toBe('ready');
    const m = useStore.getState().metrics;
    expect(m.get('00001')?.insurance_pctile).toBe(11);
    expect(m.get('00002')?.life_expectancy_pctile).toBe(22);
  });
});
