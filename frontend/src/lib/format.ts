export const fmtInt = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? '--' : Math.round(v).toLocaleString('en-US');

export const fmtMoney = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? '--' : `$${Math.round(v).toLocaleString('en-US')}`;

export const fmtScore = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? '--' : v.toFixed(0);

// Severity of an access-disadvantage percentile (higher = more disadvantage): a plain word + an
// intuitive green->amber->red tint. Single source so the detail headline and the compare table
// signal "higher = worse" identically. Every hue is darkened to clear WCAG 1.4.3 AA contrast
// (>=4.5:1 on white) so the colored score number and band labels stay legible as text, not just
// decoration. The badge sits next to the "/ 100 · disadvantage rank" headline, so the word alone
// (no noun) reads as the magnitude of disadvantage.
export function severity(p: number | null | undefined): { label: string; color: string } | null {
  if (p == null || Number.isNaN(p)) return null;
  if (p >= 80) return { label: 'Highest', color: '#B0382E' }; // red, 6.08:1
  if (p >= 60) return { label: 'High', color: '#AF6024' }; // orange, 4.63:1
  if (p >= 40) return { label: 'Moderate', color: '#907021' }; // amber, 4.64:1
  if (p >= 20) return { label: 'Low', color: '#547F3E' }; // olive-green, 4.67:1
  return { label: 'Lowest', color: '#2A8365' }; // teal-green, 4.63:1
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
