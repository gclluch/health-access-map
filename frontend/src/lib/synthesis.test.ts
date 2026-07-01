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

  it('names the top pair (not "roughly equally") when two lead and a third trails', () => {
    // shares ~40/37/23: top two near-tied but social vulnerability trails -> "mainly by ... and ..."
    const m = makeMetric({ health_need_pctile: 87, social_vulnerability_pctile: 58, care_access_pctile: 82 });
    const s = synthesize(m, W);
    expect(s).toMatch(/driven mainly by health need and barriers to care/);
    expect(s).not.toMatch(/roughly equally/);
  });

  it('says "roughly equally" only when all three shares are close', () => {
    const m = makeMetric({ health_need_pctile: 60, social_vulnerability_pctile: 58, care_access_pctile: 59 });
    expect(synthesize(m, W)).toMatch(/roughly equally across the dimensions/);
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
    expect(profile(m, W)?.kind).toBe('need-driven');
  });

  it('is access-driven when barriers clearly outweigh population need', () => {
    const m = makeMetric({ health_need_pctile: 25, social_vulnerability_pctile: 30, care_access_pctile: 90 });
    expect(profile(m, W)?.kind).toBe('access-driven');
  });

  it('is both when need and access are close (within the lean threshold)', () => {
    const m = makeMetric({ health_need_pctile: 80, social_vulnerability_pctile: 82, care_access_pctile: 78 });
    expect(profile(m, W)?.kind).toBe('both');
  });

  it('distinguishes a need-driven from an access-driven ZIP at the SAME composite level', () => {
    // both average to ~60 across the three dims, but lean opposite ways -> different interventions
    const needZip = makeMetric({ health_need_pctile: 90, social_vulnerability_pctile: 70, care_access_pctile: 20 });
    const accessZip = makeMetric({ health_need_pctile: 20, social_vulnerability_pctile: 30, care_access_pctile: 90 });
    expect(profile(needZip, W)?.kind).toBe('need-driven');
    expect(profile(accessZip, W)?.kind).toBe('access-driven');
  });

  it('responds to the weights: zeroing social vulnerability shifts the need side', () => {
    // need=(hn+sv) leans "both" at equal weight but "need-driven" once sv is dropped and hn dominates
    const m = makeMetric({ health_need_pctile: 90, social_vulnerability_pctile: 40, care_access_pctile: 70 });
    expect(profile(m, W)?.kind).toBe('both');
    expect(profile(m, { health_need: 100, social_vulnerability: 0, care_access: 35 })?.kind).toBe('need-driven');
  });

  it('returns null when the care-access dimension is missing', () => {
    const m = makeMetric({ health_need_pctile: 80, social_vulnerability_pctile: 70, care_access_pctile: null });
    expect(profile(m, W)).toBeNull();
  });

  it('flags the compounding case (both high) distinctly in its blurb', () => {
    const high = makeMetric({ health_need_pctile: 90, social_vulnerability_pctile: 88, care_access_pctile: 85 });
    const low = makeMetric({ health_need_pctile: 20, social_vulnerability_pctile: 22, care_access_pctile: 18 });
    expect(profile(high, W)?.blurb).toMatch(/compounding/);
    expect(profile(low, W)?.blurb).toMatch(/not concentrated on the demand or the supply side/);
  });
});
