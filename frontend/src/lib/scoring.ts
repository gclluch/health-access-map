import { COMPOSITE_METRIC, type SlimMetric, type Weights } from './types';

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

// Value used to color the map / drive rankings for the active metric column.
export function metricValue(m: SlimMetric, metric: string, w: Weights): number | null {
  if (metric === COMPOSITE_METRIC) return accessGap(m, w);
  const v = m[metric];
  return typeof v === 'number' ? v : null;
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
