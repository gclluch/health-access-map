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
  let driver = 'multiple factors';
  if (contrib) {
    const entries = Object.entries(contrib) as Array<
      ['health_need' | 'social_vulnerability' | 'care_access', number]
    >;
    entries.sort((a, b) => b[1] - a[1]);
    driver = {
      health_need: 'health need',
      social_vulnerability: 'social vulnerability',
      care_access: 'barriers to care',
    }[entries[0][0]];
  }

  return (
    `${need[0].toUpperCase()}${need.slice(1)} health need, ${vuln} social vulnerability, ` +
    `and ${access} barriers to care. The access gap here is driven mostly by ${driver}.`
  );
}
