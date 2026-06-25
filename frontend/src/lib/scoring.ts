import { COMPOSITE_METRIC, COMPOSITE_MULT_METRIC, type SlimMetric, type Weights } from './types';

// Client-side Access Gap = weighted mean of the 3 dimension percentiles
// (health need, social vulnerability, care access), renormalized over whichever
// dimensions are present. Mirrors the pipeline composite; the sliders re-weight live.
export function accessGap(m: SlimMetric, w: Weights): number | null {
  if (!m.scoreable) return null;
  const eff =
    w.health_need + w.social_vulnerability + w.care_access <= 0
      ? { health_need: 1, social_vulnerability: 1, care_access: 1 }
      : w;
  const parts: Array<[number, number]> = [];
  if (m.health_need_pctile != null) parts.push([eff.health_need, m.health_need_pctile]);
  if (m.social_vulnerability_pctile != null)
    parts.push([eff.social_vulnerability, m.social_vulnerability_pctile]);
  if (m.care_access_pctile != null) parts.push([eff.care_access, m.care_access_pctile]);
  if (parts.length < 2) return null;
  const wsum = parts.reduce((a, [pw]) => a + pw, 0);
  if (wsum <= 0) return null;
  return parts.reduce((a, [pw, v]) => a + pw * v, 0) / wsum;
}

// Multiplicative "coincidence" lens: weighted GEOMETRIC mean of the 3 dimension
// percentiles (mirrors pipeline access_gap_mult / OECD non-compensatory aggregation).
// A deficit in one dimension can't be offset by surplus in another, so it only lights
// up where need AND barriers coincide. Frac clipped to [0.01,1] so a 0-rank dim can't
// zero the product; renormalized over present dims. Same 0-100 scale as accessGap.
export function accessGapMult(m: SlimMetric, w: Weights): number | null {
  if (!m.scoreable) return null;
  const eff =
    w.health_need + w.social_vulnerability + w.care_access <= 0
      ? { health_need: 1, social_vulnerability: 1, care_access: 1 }
      : w;
  const parts: Array<[number, number]> = [];
  if (m.health_need_pctile != null) parts.push([eff.health_need, m.health_need_pctile]);
  if (m.social_vulnerability_pctile != null)
    parts.push([eff.social_vulnerability, m.social_vulnerability_pctile]);
  if (m.care_access_pctile != null) parts.push([eff.care_access, m.care_access_pctile]);
  if (parts.length < 2) return null;
  const wsum = parts.reduce((a, [pw]) => a + pw, 0);
  if (wsum <= 0) return null;
  const lognum = parts.reduce(
    (a, [pw, v]) => a + pw * Math.log(Math.min(1, Math.max(0.01, v / 100))),
    0,
  );
  return Math.exp(lognum / wsum) * 100;
}

// Parse a "w=h,s,c" URL param into Weights, rejecting anything malformed: must be exactly 3
// finite, non-negative numbers that don't all sum to 0. Negatives would invert a dimension and
// render a misleading map from a crafted link, so they're refused (returns null -> caller keeps
// defaults). Pure + exported so it can be unit-tested without the store's side effects.
export function parseWeightParam(w: string | null): Weights | null {
  if (!w) return null;
  const parts = w.split(',').map(Number);
  if (parts.length !== 3) return null;
  if (!parts.every((n) => Number.isFinite(n) && n >= 0)) return null;
  if (parts.reduce((a, b) => a + b, 0) <= 0) return null;
  const [health_need, social_vulnerability, care_access] = parts;
  return { health_need, social_vulnerability, care_access };
}

// Value used to color the map / drive rankings for the active metric column.
export function metricValue(m: SlimMetric, metric: string, w: Weights): number | null {
  if (metric === COMPOSITE_METRIC) return accessGap(m, w);
  if (metric === COMPOSITE_MULT_METRIC) return accessGapMult(m, w);
  const v = m[metric];
  return typeof v === 'number' ? v : null;
}

// Sorted (ascending) array of every scoreable area's live access-gap value, for converting a
// single area's value into its national percentile under the CURRENT weights (the additive
// composite is re-ranked at the dimension level server-side, but re-weighting needs a live rank).
export function buildScoreIndex(metrics: Iterable<SlimMetric>, w: Weights): number[] {
  const arr: number[] = [];
  for (const m of metrics) {
    const s = accessGap(m, w);
    if (s != null) arr.push(s);
  }
  return arr.sort((a, b) => a - b);
}

// National percentile of `score` within a sorted index from buildScoreIndex (binary search).
export function percentileOf(sorted: number[], score: number | null): number | null {
  if (score == null || !sorted.length) return null;
  let lo = 0;
  let hi = sorted.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (sorted[mid] < score) lo = mid + 1;
    else hi = mid;
  }
  return (lo / sorted.length) * 100;
}

// Contribution of each dimension to the composite (weight-normalized; sums to score).
export function dimensionContributions(
  m: SlimMetric,
  w: Weights,
): { health_need: number; social_vulnerability: number; care_access: number } | null {
  if (accessGap(m, w) == null) return null;
  const eff =
    w.health_need + w.social_vulnerability + w.care_access <= 0
      ? { health_need: 1, social_vulnerability: 1, care_access: 1 }
      : w;
  const parts: Array<['health_need' | 'social_vulnerability' | 'care_access', number, number]> = [];
  if (m.health_need_pctile != null) parts.push(['health_need', eff.health_need, m.health_need_pctile]);
  if (m.social_vulnerability_pctile != null)
    parts.push(['social_vulnerability', eff.social_vulnerability, m.social_vulnerability_pctile]);
  if (m.care_access_pctile != null) parts.push(['care_access', eff.care_access, m.care_access_pctile]);
  const wsum = parts.reduce((a, [, pw]) => a + pw, 0) || 1;
  const out = { health_need: 0, social_vulnerability: 0, care_access: 0 };
  for (const [k, pw, v] of parts) out[k] = (pw / wsum) * v;
  return out;
}
