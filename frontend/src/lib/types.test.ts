import { describe, it, expect } from 'vitest';
import { makeMetric } from './testFactory';
import {
  COMPOSITE_METRIC,
  COMPOSITE_MULT_METRIC,
  WITHIN_STATE_METRIC,
  ACCESS_RESID_METRIC,
  isCompositeFamily,
  isPartialScore,
} from './types';

describe('isCompositeFamily (T2 gate scope)', () => {
  it('is true for the composite and its derived lenses', () => {
    expect(isCompositeFamily(COMPOSITE_METRIC)).toBe(true);
    expect(isCompositeFamily(COMPOSITE_MULT_METRIC)).toBe(true);
    expect(isCompositeFamily(WITHIN_STATE_METRIC)).toBe(true);
    expect(isCompositeFamily(ACCESS_RESID_METRIC)).toBe(true);
    expect(isCompositeFamily('access_gap_pctile')).toBe(true);
  });

  it('is false for bare dimension / sub-score percentiles (they stay comparable when present)', () => {
    expect(isCompositeFamily('care_access_pctile')).toBe(false);
    expect(isCompositeFamily('health_need_pctile')).toBe(false);
    expect(isCompositeFamily('provider_supply_pctile')).toBe(false);
  });
});

describe('isPartialScore (2-of-3 composite)', () => {
  it('flags a 2-dim composite as partial', () => {
    expect(isPartialScore(makeMetric({ n_dims_scored: 2 }))).toBe(true);
  });

  it('does not flag a full 3-dim composite', () => {
    expect(isPartialScore(makeMetric({ n_dims_scored: 3 }))).toBe(false);
  });

  it('does not flag when n_dims_scored is unknown (null)', () => {
    expect(isPartialScore(makeMetric({ n_dims_scored: null }))).toBe(false);
  });
});
