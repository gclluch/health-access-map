import { describe, it, expect } from 'vitest';
import { accessGap, accessGapMult, dimensionContributions, metricValue, parseWeightParam } from './scoring';
import { makeMetric } from './testFactory';
import { COMPOSITE_METRIC, COMPOSITE_MULT_METRIC, type Weights } from './types';

const W: Weights = { health_need: 35, social_vulnerability: 30, care_access: 35 };

describe('accessGap', () => {
  it('is the weighted mean of the three dimension percentiles', () => {
    const m = makeMetric({ health_need_pctile: 80, social_vulnerability_pctile: 50, care_access_pctile: 20 });
    const expected = (35 * 80 + 30 * 50 + 35 * 20) / 100;
    expect(accessGap(m, W)).toBeCloseTo(expected, 6);
  });

  it('renormalizes over present dimensions when one is missing', () => {
    const m = makeMetric({ health_need_pctile: 80, social_vulnerability_pctile: 40, care_access_pctile: null });
    expect(accessGap(m, W)).toBeCloseTo((35 * 80 + 30 * 40) / 65, 6);
  });

  it('returns null when fewer than two dimensions are present', () => {
    const m = makeMetric({ health_need_pctile: 80, social_vulnerability_pctile: null, care_access_pctile: null });
    expect(accessGap(m, W)).toBeNull();
  });

  it('returns null for non-scoreable areas', () => {
    expect(accessGap(makeMetric({ scoreable: false }), W)).toBeNull();
  });

  it('falls back to equal weighting when all weights are zero', () => {
    const m = makeMetric({ health_need_pctile: 90, social_vulnerability_pctile: 60, care_access_pctile: 30 });
    expect(accessGap(m, { health_need: 0, social_vulnerability: 0, care_access: 0 })).toBeCloseTo((90 + 60 + 30) / 3, 6);
  });
});

describe('accessGapMult (coincidence lens)', () => {
  it('equals the additive mean when all dimensions are equal', () => {
    const m = makeMetric({ health_need_pctile: 50, social_vulnerability_pctile: 50, care_access_pctile: 50 });
    expect(accessGapMult(m, W)).toBeCloseTo(50, 4);
  });

  it('is non-compensatory: penalizes one-dimensional highs vs the additive mean', () => {
    const m = makeMetric({ health_need_pctile: 100, social_vulnerability_pctile: 100, care_access_pctile: 10 });
    const add = accessGap(m, W)!;
    const mult = accessGapMult(m, W)!;
    expect(mult).toBeLessThan(add); // a deficit in one dim drags the geometric mean below the arithmetic
  });

  it('clips a zero-rank dimension to 0.01 so the product is never zeroed', () => {
    const m = makeMetric({ health_need_pctile: 0, social_vulnerability_pctile: 50, care_access_pctile: 50 });
    expect(accessGapMult(m, W)).toBeGreaterThan(0);
  });
});

describe('dimensionContributions', () => {
  it('sum to the additive access gap', () => {
    const m = makeMetric({ health_need_pctile: 70, social_vulnerability_pctile: 40, care_access_pctile: 90 });
    const c = dimensionContributions(m, W)!;
    const sum = c.health_need + c.social_vulnerability + c.care_access;
    expect(sum).toBeCloseTo(accessGap(m, W)!, 6);
  });
});

describe('parseWeightParam', () => {
  it('accepts three finite non-negative weights', () => {
    expect(parseWeightParam('35,30,35')).toEqual({ health_need: 35, social_vulnerability: 30, care_access: 35 });
    expect(parseWeightParam('0,0,1')).toEqual({ health_need: 0, social_vulnerability: 0, care_access: 1 });
  });
  it('rejects negatives, non-finite, wrong arity, and all-zero (crafted-URL footgun)', () => {
    expect(parseWeightParam('-50,100,0')).toBeNull(); // negative would invert a dimension
    expect(parseWeightParam('0,0,0')).toBeNull(); // sums to 0 -> undefined renorm
    expect(parseWeightParam('1,2')).toBeNull(); // wrong arity
    expect(parseWeightParam('1,2,3,4')).toBeNull();
    expect(parseWeightParam('a,b,c')).toBeNull(); // NaN
    expect(parseWeightParam('1,1e999,1')).toBeNull(); // Infinity
    expect(parseWeightParam('')).toBeNull();
    expect(parseWeightParam(null)).toBeNull();
  });
});

describe('metricValue', () => {
  it('routes composite metrics through the recompute and sub-scores to their raw value', () => {
    const m = makeMetric({ health_need_pctile: 60, social_vulnerability_pctile: 60, care_access_pctile: 60, insurance_pctile: 42 });
    expect(metricValue(m, COMPOSITE_METRIC, W)).toBeCloseTo(60, 6);
    expect(typeof metricValue(m, COMPOSITE_MULT_METRIC, W)).toBe('number');
    expect(metricValue(m, 'insurance_pctile', W)).toBe(42);
  });
});
