import { describe, it, expect, vi, afterEach } from 'vitest';
import { apiZcta, apiCompare } from './api';

// T10: production is static-only. Both drill-down and compare read the per-ZIP3 shards
// (/zcta/{zip3}.json) - never a dynamic /api endpoint. Guard that contract.
describe('static-only shard data path (T10)', () => {
  afterEach(() => vi.unstubAllGlobals());

  // Distinct zip3 prefixes per test so the module-level shard cache doesn't bleed between cases.
  const shards: Record<string, Record<string, { pop: number }>> = {
    '/zcta/900.json': { '90001': { pop: 1 } },
    '/zcta/941.json': { '94102': { pop: 2 } },
  };
  const mockFetch = () => {
    const fn = vi.fn(async (url: string) =>
      shards[url]
        ? { ok: true, json: async () => shards[url] }
        : { ok: false, status: 404, json: async () => ({}) });
    vi.stubGlobal('fetch', fn);
    return fn;
  };

  it('apiZcta reads the shard, not /api', async () => {
    const fn = mockFetch();
    const rec = await apiZcta('90001');
    expect(rec).toEqual({ pop: 1 });
    expect(fn).toHaveBeenCalledWith('/zcta/900.json', expect.anything());
    expect(fn.mock.calls.every(([u]) => !String(u).includes('/api'))).toBe(true);
  });

  it('apiCompare enriches from shards and drops missing ZIPs (best-effort)', async () => {
    const fn = mockFetch();
    const { results } = await apiCompare(['94102', '94199']);
    expect(results).toEqual([{ pop: 2, zcta5: '94102' }]); // 94199 absent -> dropped, not thrown
    expect(fn.mock.calls.some(([u]) => u === '/zcta/941.json')).toBe(true);
    expect(fn.mock.calls.every(([u]) => !String(u).includes('/api'))).toBe(true);
  });
});
