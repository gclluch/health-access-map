import { describe, it, expect } from 'vitest';
import { synthesize, profile } from './synthesis';
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

describe('profile (need-vs-access lever)', () => {
  it('is need-driven when need + vulnerability clearly outweigh barriers', () => {
    const m = makeMetric({ health_need_pctile: 90, social_vulnerability_pctile: 85, care_access_pctile: 30 });
    expect(profile(m)?.kind).toBe('need-driven');
  });

  it('is access-driven when barriers clearly outweigh population need', () => {
    const m = makeMetric({ health_need_pctile: 25, social_vulnerability_pctile: 30, care_access_pctile: 90 });
    expect(profile(m)?.kind).toBe('access-driven');
  });

  it('is both when need and access are close (within the lean threshold)', () => {
    const m = makeMetric({ health_need_pctile: 80, social_vulnerability_pctile: 82, care_access_pctile: 78 });
    expect(profile(m)?.kind).toBe('both');
  });

  it('distinguishes a need-driven from an access-driven ZIP at the SAME composite level', () => {
    // both average to ~60 across the three dims, but lean opposite ways -> different interventions
    const needZip = makeMetric({ health_need_pctile: 90, social_vulnerability_pctile: 70, care_access_pctile: 20 });
    const accessZip = makeMetric({ health_need_pctile: 20, social_vulnerability_pctile: 30, care_access_pctile: 90 });
    expect(profile(needZip)?.kind).toBe('need-driven');
    expect(profile(accessZip)?.kind).toBe('access-driven');
  });

  it('returns null when the care-access dimension is missing', () => {
    const m = makeMetric({ health_need_pctile: 80, social_vulnerability_pctile: 70, care_access_pctile: null });
    expect(profile(m)).toBeNull();
  });

  it('flags the compounding case (both high) distinctly in its blurb', () => {
    const high = makeMetric({ health_need_pctile: 90, social_vulnerability_pctile: 88, care_access_pctile: 85 });
    const low = makeMetric({ health_need_pctile: 20, social_vulnerability_pctile: 22, care_access_pctile: 18 });
    expect(profile(high)?.blurb).toMatch(/compounding/);
    expect(profile(low)?.blurb).toMatch(/no single lever/);
  });
});
