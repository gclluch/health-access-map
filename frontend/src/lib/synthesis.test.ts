import { describe, it, expect } from 'vitest';
import { synthesize } from './synthesis';
import { makeMetric } from './testFactory';
import type { Weights } from './types';

const W: Weights = { health_need: 35, social_vulnerability: 30, care_access: 35 };

describe('synthesize', () => {
  it('names the dominant contributing dimension', () => {
    // care access percentile dominates -> driver should be "barriers to care"
    const m = makeMetric({ health_need_pctile: 20, social_vulnerability_pctile: 20, care_access_pctile: 95 });
    expect(synthesize(m, W)).toMatch(/barriers to care/);
  });

  it('describes each dimension band (high/moderate/low)', () => {
    const m = makeMetric({ health_need_pctile: 80, social_vulnerability_pctile: 50, care_access_pctile: 10 });
    const s = synthesize(m, W);
    expect(s).toMatch(/^High health need/);
    expect(s).toMatch(/moderate social vulnerability/);
    expect(s).toMatch(/low barriers to care/);
  });
});
