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

export function profile(m: SlimMetric): Profile | null {
  const needParts = [m.health_need_pctile, m.social_vulnerability_pctile].filter(
    (v): v is number => v != null,
  );
  const access = m.care_access_pctile;
  if (!needParts.length || access == null) return null;
  const need = needParts.reduce((a, b) => a + b, 0) / needParts.length;
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
      : 'Need and barriers contribute roughly equally here - no single lever dominates.',
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
    const entries = (Object.entries(contrib) as Array<
      ['health_need' | 'social_vulnerability' | 'care_access', number]
    >).sort((a, b) => b[1] - a[1]);
    const total = entries.reduce((s, [, v]) => s + v, 0) || 1;
    const label = {
      health_need: 'health need',
      social_vulnerability: 'social vulnerability',
      care_access: 'barriers to care',
    }[entries[0][0]];
    // The dimensions are collinear and weights near-equal, so shares are often ~even; only call
    // out a single driver when the top one materially leads (>=10 share points over the next).
    const topLead = entries[0][1] / total - (entries[1]?.[1] ?? 0) / total;
    tail = topLead >= 0.1 ? `driven mostly by ${label}` : 'driven roughly equally across the dimensions';
  }

  return (
    `${need[0].toUpperCase()}${need.slice(1)} health need, ${vuln} social vulnerability, ` +
    `and ${access} barriers to care. The access disadvantage here is ${tail}.`
  );
}
