import { useEffect, useMemo, useState } from 'react';
import { useStore } from '../store';
import { accessGap, buildScoreIndex, percentileOf } from '../lib/scoring';
import { downloadCsv } from '../lib/csv';
import { apiCompare, type ApiZcta } from '../lib/api';
import { fmtInt, fmtMoney, ordinal } from '../lib/format';

const DIM_ROWS: Array<[string, 'health_need_pctile' | 'social_vulnerability_pctile' | 'care_access_pctile']> = [
  ['Health need', 'health_need_pctile'],
  ['Social vulnerability', 'social_vulnerability_pctile'],
  ['Barriers to care', 'care_access_pctile'],
];

// Side-by-side comparison of 2-5 ZIPs. Headline rows (national rank, tier, the 3 dimensions)
// come from the in-memory slim metrics so it works with no backend; median income / poverty /
// uninsured are enriched best-effort via the /api/compare endpoint and simply omitted if it's down.
export default function CompareTray() {
  const metrics = useStore((s) => s.metrics);
  const weights = useStore((s) => s.weights);
  const compareZctas = useStore((s) => s.compareZctas);
  const removeCompare = useStore((s) => s.removeCompare);
  const clearCompare = useStore((s) => s.clearCompare);
  const select = useStore((s) => s.select);
  const [extra, setExtra] = useState<Record<string, ApiZcta>>({});

  const sorted = useMemo(() => buildScoreIndex(metrics.values(), weights), [metrics, weights]);

  useEffect(() => {
    if (compareZctas.length === 0) {
      setExtra({});
      return;
    }
    let live = true;
    apiCompare(compareZctas)
      .then((r) => {
        if (!live) return;
        const map: Record<string, ApiZcta> = {};
        for (const rec of r.results) map[rec.zcta5] = rec;
        setExtra(map);
      })
      .catch(() => {
        /* API optional: the dimension rows still render from the slim metrics */
      });
    return () => {
      live = false;
    };
  }, [compareZctas]);

  const cols = useMemo(
    () =>
      compareZctas.map((z) => {
        const m = metrics.get(z);
        const score = m ? accessGap(m, weights) : null;
        return { z, m, score, pct: percentileOf(sorted, score), ex: extra[z] };
      }),
    [compareZctas, metrics, weights, sorted, extra],
  );

  if (compareZctas.length === 0) return null;

  const num = (v: unknown) => (typeof v === 'number' ? v : null);

  const exportCsv = () => {
    const rows = cols.map(({ z, m, pct, ex }) => ({
      zip: z,
      place: m?.city ?? m?.county_name ?? '',
      state: m?.state ?? '',
      access_gap_rank: pct != null ? Math.round(pct) : '',
      tier: m?.tier ?? '',
      health_need_pctile: m?.health_need_pctile ?? '',
      social_vulnerability_pctile: m?.social_vulnerability_pctile ?? '',
      care_access_pctile: m?.care_access_pctile ?? '',
      population: m?.population ?? '',
      median_income: num(ex?.median_income) ?? '',
      poverty_rate: num(ex?.poverty_rate) ?? '',
      uninsured_rate: num(ex?.uninsured_rate) ?? '',
    }));
    downloadCsv(`access-gap-compare-${compareZctas.join('-')}.csv`, rows);
  };

  const cell = 'px-2 py-1 text-right num text-[11px] tabular-nums border-l border-hairline/60';

  return (
    <div className="panel rounded-md overflow-hidden w-full" role="region" aria-label="ZIP comparison">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-hairline">
        <span className="text-[12px] font-medium text-ink">Compare ZIPs ({compareZctas.length}/5)</span>
        <div className="flex items-center gap-2">
          <button onClick={exportCsv} className="text-[11px] text-accent hover:underline" title="Download this comparison as CSV">
            ⬇ CSV
          </button>
          <button onClick={clearCompare} className="text-[11px] text-graphite hover:text-ink">
            Clear
          </button>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-hairline">
              <th className="px-2 py-1 text-left text-[10px] uppercase tracking-wide text-graphite font-normal">Metric</th>
              {cols.map(({ z, m }) => (
                <th key={z} className="px-2 py-1 text-right border-l border-hairline/60">
                  <button
                    onClick={() => select(z, { fly: true })}
                    className="text-[11px] text-ink font-medium hover:text-accent block w-full truncate text-right"
                    title={`${m?.city ?? m?.county_name ?? z} - view on map`}
                  >
                    {m?.city ?? m?.county_name ?? z}
                  </button>
                  <div className="flex items-center justify-end gap-1">
                    <span className="num text-[10px] text-graphite">{z}</span>
                    <button onClick={() => removeCompare(z)} aria-label={`Remove ${z}`} className="text-[10px] text-graphite hover:text-rose-500">
                      ✕
                    </button>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="text-ink">
            <tr className="border-b border-hairline/60 bg-paper/40">
              <td className="px-2 py-1 text-[11px] text-graphite">National access-gap rank</td>
              {cols.map(({ z, pct }) => (
                <td key={z} className={cell + ' font-semibold'}>{pct != null ? ordinal(pct) : '--'}</td>
              ))}
            </tr>
            <tr className="border-b border-hairline/60">
              <td className="px-2 py-1 text-[11px] text-graphite">Tier (1-10)</td>
              {cols.map(({ z, m }) => (
                <td key={z} className={cell}>{m?.tier ?? '--'}</td>
              ))}
            </tr>
            {DIM_ROWS.map(([label, key]) => (
              <tr key={key} className="border-b border-hairline/60">
                <td className="px-2 py-1 text-[11px] text-graphite">{label}</td>
                {cols.map(({ z, m }) => {
                  const v = num(m?.[key]);
                  return <td key={z} className={cell}>{v != null ? ordinal(v) : '--'}</td>;
                })}
              </tr>
            ))}
            <tr className="border-b border-hairline/60">
              <td className="px-2 py-1 text-[11px] text-graphite">Population</td>
              {cols.map(({ z, m }) => (
                <td key={z} className={cell}>{fmtInt(num(m?.population))}</td>
              ))}
            </tr>
            <tr className="border-b border-hairline/60">
              <td className="px-2 py-1 text-[11px] text-graphite">Median income</td>
              {cols.map(({ z, ex }) => (
                <td key={z} className={cell}>{fmtMoney(num(ex?.median_income))}</td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
