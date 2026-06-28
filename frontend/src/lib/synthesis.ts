import type { SlimMetric, Weights } from './types';
import { dimensionContributions } from './scoring';

const band = (p: number | null | undefined) =>
  p == null ? 'unknown' : p >= 66 ? 'high' : p <= 33 ? 'low' : 'moderate';

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
