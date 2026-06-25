export const fmtPct1 = (v: number | null | undefined, suffix = '%') =>
  v == null || Number.isNaN(v) ? '--' : `${v.toFixed(1)}${suffix}`;

export const fmtRatePct = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? '--' : `${(v * 100).toFixed(1)}%`;

export const fmtInt = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? '--' : Math.round(v).toLocaleString('en-US');

export const fmtMoney = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? '--' : `$${Math.round(v).toLocaleString('en-US')}`;

export const fmtScore = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? '--' : v.toFixed(0);

export const fmtPer1k = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? '--' : v.toFixed(1);

// Severity of an access-gap percentile (higher = worse access): a plain word + an intuitive
// green->amber->red tint. Muted, desaturated hues to sit with the palette. Single source so the
// detail headline and the compare table signal "higher = worse" identically.
export function severity(p: number | null | undefined): { label: string; color: string } | null {
  if (p == null || Number.isNaN(p)) return null;
  if (p >= 80) return { label: 'Severe gap', color: '#B0382E' }; // red
  if (p >= 60) return { label: 'High gap', color: '#C06A28' }; // orange
  if (p >= 40) return { label: 'Moderate gap', color: '#B8902A' }; // amber
  if (p >= 20) return { label: 'Below average', color: '#5E8F46' }; // olive-green
  return { label: 'Low gap', color: '#2C8A6A' }; // teal-green
}

// "worse than 78% of ZIPs" reading for a percentile (correct st/nd/rd/th suffix).
export const ordinal = (v: number | null | undefined) => {
  if (v == null || Number.isNaN(v)) return '--';
  const n = Math.round(v);
  const rem100 = n % 100;
  const rem10 = n % 10;
  const suffix =
    rem100 >= 11 && rem100 <= 13 ? 'th' : rem10 === 1 ? 'st' : rem10 === 2 ? 'nd' : rem10 === 3 ? 'rd' : 'th';
  return `${n}${suffix}`;
};
