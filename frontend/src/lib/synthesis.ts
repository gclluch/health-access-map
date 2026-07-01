import type { SlimMetric, Weights } from './types';
import { dimensionContributions } from './scoring';

const band = (p: number | null | undefined) =>
  p == null ? 'unknown' : p >= 66 ? 'high' : p <= 33 ? 'low' : 'moderate';

export type ProfileKind = 'need-driven' | 'access-driven' | 'both';

export interface Profile {
  kind: ProfileKind;
  label: string;
  blurb: string;
}

// Which lever the access disadvantage points to. A 90th-percentile composite can be almost all
// population health need or almost all no-providers - different interventions - so this need-vs-
// access split is the actionable signal the single conflated number hides (T5). Decided on the
// percentile gap between the NEED side (mean of health need + social vulnerability, the demand the
// area places on care) and the ACCESS side (care_access, the barriers to reaching it). The three
// dimensions are collinear (~1.6 effective dims), so most ZIPs land in "both"; a clear lean is the
// informative case. PROFILE_LEAN mirrors the "materially leads" threshold used in synthesize().
const PROFILE_LEAN = 15;

export function profile(m: SlimMetric, w: Weights): Profile | null {
  const access = m.care_access_pctile;
  if (access == null) return null;
  // Weight the need side (health need + social vulnerability) by the sliders so this lever responds
  // to re-weighting consistently with synthesize(); fall back to equal weight if both are zeroed.
  const needParts: Array<[number, number]> = [];
  if (m.health_need_pctile != null) needParts.push([w.health_need, m.health_need_pctile]);
  if (m.social_vulnerability_pctile != null) needParts.push([w.social_vulnerability, m.social_vulnerability_pctile]);
  if (!needParts.length) return null;
  const wsum = needParts.reduce((a, [pw]) => a + pw, 0);
  const need = wsum > 0
    ? needParts.reduce((a, [pw, v]) => a + pw * v, 0) / wsum
    : needParts.reduce((a, [, v]) => a + v, 0) / needParts.length;
  const gap = need - access;
  if (gap >= PROFILE_LEAN)
    return {
      kind: 'need-driven',
      label: 'Need-driven',
      blurb:
        'Health need and social vulnerability outweigh care barriers here - the levers are coverage, ' +
        'outreach, and chronic-care capacity, not more clinics alone.',
    };
  if (gap <= -PROFILE_LEAN)
    return {
      kind: 'access-driven',
      label: 'Access-driven',
      blurb:
        'Barriers to care outweigh the underlying population need here - the levers are clinicians, ' +
        'transport, and safety-net siting.',
    };
  const bothHigh = need >= 66 && access >= 66;
  return {
    kind: 'both',
    label: 'Need + access',
    blurb: bothHigh
      ? 'High health need and hard-to-reach care coincide here - the compounding case for combined ' +
        'demand- and supply-side action.'
      : 'Population need and barriers to care are close here, so the disadvantage is not concentrated ' +
        'on the demand or the supply side (a single dimension may still lead - see the breakdown).',
  };
}

// One-sentence, plain, specific read generated from the dimension percentiles.
export function synthesize(m: SlimMetric, w: Weights): string {
  const need = band(m.health_need_pctile);
  const vuln = band(m.social_vulnerability_pctile);
  const access = band(m.care_access_pctile);

  const contrib = dimensionContributions(m, w);
  let tail = 'driven by several factors together';
  if (contrib) {
    const LABELS = {
      health_need: 'health need',
      social_vulnerability: 'social vulnerability',
      care_access: 'barriers to care',
    } as const;
    const entries = (Object.entries(contrib) as Array<[keyof typeof LABELS, number]>)
      .sort((a, b) => b[1] - a[1]);
    const total = entries.reduce((s, [, v]) => s + v, 0) || 1;
    const [s0, s1, s2] = entries.map(([, v]) => v / total);
    // "Roughly equal" requires all THREE shares to be close, not just the top pair: a near-tied
    // top two over a trailing third (e.g. 40/37/23) reads as driven by that pair, not evenly.
    if (s0 - s1 >= 0.1) tail = `driven mostly by ${LABELS[entries[0][0]]}`;
    else if (s0 - s2 < 0.1) tail = 'driven roughly equally across the dimensions';
    else tail = `driven mainly by ${LABELS[entries[0][0]]} and ${LABELS[entries[1][0]]}`;
  }

  return (
    `${need[0].toUpperCase()}${need.slice(1)} health need, ${vuln} social vulnerability, ` +
    `and ${access} barriers to care. The access disadvantage here is ${tail}.`
  );
}
