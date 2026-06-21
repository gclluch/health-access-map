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
