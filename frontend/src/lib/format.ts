export const fmtInt = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? '--' : Math.round(v).toLocaleString('en-US');

export const fmtMoney = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? '--' : `$${Math.round(v).toLocaleString('en-US')}`;

export const fmtScore = (v: number | null | undefined) =>
  v == null || Number.isNaN(v) ? '--' : v.toFixed(0);

// Severity of an access-disadvantage percentile (higher = more disadvantage): a plain word + an
// intuitive green->amber->red tint. Single source so the detail headline and the compare table
// signal "higher = worse" identically. The badge sits next to the "/ 100 · screening priority"
// headline, so the word alone (no noun) reads as the magnitude of disadvantage.
//
// Each hue clears WCAG 1.4.3 AA (>=4.5:1) against the DARKER of its two backgrounds: the badge
// paints the same hue at 8% over white (`${color}14`), which costs ~0.4 of the ratio the colour
// has on white. Calibrating against white alone leaves the badge text just under AA. Ratios below
// are on the tint; on plain white every hue is >=5:1.
export function severity(p: number | null | undefined): { label: string; color: string } | null {
  if (p == null || Number.isNaN(p)) return null;
  if (p >= 80) return { label: 'Highest', color: '#B0382E' }; // red, 5.41:1
  if (p >= 60) return { label: 'High', color: '#A55B22' }; // orange, 4.60:1
  if (p >= 40) return { label: 'Moderate', color: '#886A1F' }; // amber, 4.61:1
  if (p >= 20) return { label: 'Low', color: '#50793B' }; // olive-green, 4.61:1
  return { label: 'Lowest', color: '#277B5F' }; // teal-green, 4.63:1
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
