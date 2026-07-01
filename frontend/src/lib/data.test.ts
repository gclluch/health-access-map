import { describe, it, expect } from 'vitest';
import { framesToRecords, type ColumnFrame } from './data';

// T8: the first-paint payload is columnar (struct-of-arrays); framesToRecords rebuilds the
// SlimMetric[] the store expects. Guard the reconstruction contract (nulls, 0/1 flags, absent
// lazy columns) so a payload-shape change can't silently break cold load.
describe('framesToRecords (T8 columnar map frame)', () => {
  const frame: ColumnFrame = {
    n: 2,
    zcta5: ['01001', '01002'],
    state: ['MA', null],
    population: [4895, null],
    health_need_pctile: [61, null],
    scoreable: [1, 0],
    low_confidence: [0, 1],
    institutional: [0, 0],
  };
  const recs = framesToRecords(frame);

  it('reconstructs one record per row, keyed by zcta5', () => {
    expect(recs).toHaveLength(2);
    expect(recs[0].zcta5).toBe('01001');
    expect(recs[1].zcta5).toBe('01002');
  });

  it('passes strings/numbers through and preserves nulls', () => {
    expect(recs[0].state).toBe('MA');
    expect(recs[1].state).toBeNull();
    expect(recs[0].population).toBe(4895);
    expect(recs[0].health_need_pctile).toBe(61);
    expect(recs[1].health_need_pctile).toBeNull();
  });

  it('restores 0/1 flag columns to booleans', () => {
    expect(recs[0].scoreable).toBe(true);
    expect(recs[1].scoreable).toBe(false);
    expect(recs[1].low_confidence).toBe(true);
    expect(recs[0].institutional).toBe(false);
  });

  it('leaves sub-score columns absent until lazy-merged', () => {
    expect(recs[0].insurance_pctile).toBeUndefined();
  });
});
