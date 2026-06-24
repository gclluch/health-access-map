import { useMemo } from 'react';
import { useStore } from '../store';
import { metricValue } from '../lib/scoring';
import { COMPOSITE_METRIC, COMPOSITE_MULT_METRIC, metricLabel, MODEL, OUTCOME_METRICS } from '../lib/types';

// access_gap spreads 0-100; the raw-percentile metrics cluster near 100/0 at the
// ends, so show one decimal there to keep the ordering legible.
const fmtRank = (v: number, metric: string) =>
  metric === COMPOSITE_METRIC || metric === COMPOSITE_MULT_METRIC ? v.toFixed(0) : v.toFixed(1);

// Self-contained ranking: pick the metric AND the end of the range (highest /
// lowest) right here. Recomputed from the same client-side scoring so it honors
// live slider weights (§13.5). Tri-pane linked: hover highlights the polygon,
// click flies + selects (§13.1). Low-confidence ZIPs excluded from the headline.
export default function RankingsList() {
  const { metrics, metric, weights, stateFilter, selectedZcta, rankOrder } = useStore();
  const select = useStore((s) => s.select);
  const hover = useStore((s) => s.hover);
  const setMetric = useStore((s) => s.setMetric);
  const setRankOrder = useStore((s) => s.setRankOrder);

  const rows = useMemo(() => {
    const out: Array<{ z: string; v: number; label: string }> = [];
    for (const m of metrics.values()) {
      if (!m.scoreable || m.low_confidence) continue;
      if (stateFilter && m.state !== stateFilter) continue;
      const v = metricValue(m, metric, weights);
      if (v != null && !Number.isNaN(v)) {
        const label = m.city ? `${m.city}, ${m.state ?? ''}` : m.county_name ?? `ZIP ${m.zcta5}`;
        out.push({ z: m.zcta5, v, label });
      }
    }
    out.sort((a, b) => (rankOrder === 'desc' ? b.v - a.v : a.v - b.v));
    return out.slice(0, 100);
  }, [metrics, metric, weights, stateFilter, rankOrder]);

  const end = rankOrder === 'desc' ? 'Highest' : 'Lowest';

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-hairline">
        {/* metric + direction controls */}
        <div className="flex items-center gap-1.5 mb-1">
          <select
            aria-label="Rank by metric"
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
            className="flex-1 min-w-0 text-[12px] font-medium text-ink bg-transparent outline-none cursor-pointer focus:ring-2 focus:ring-accent/40 rounded"
          >
            <option value={COMPOSITE_METRIC}>Access gap (composite)</option>
            <option value={COMPOSITE_MULT_METRIC}>Access gap (coincidence lens)</option>
            {MODEL.map((d) => (
              <optgroup key={d.key} label={d.label}>
                <option value={`${d.key}_pctile`}>{d.label} (overall)</option>
                {d.subs.map((s) => (
                  <option key={s.key} value={`${s.key}_pctile`}>
                    &nbsp;&nbsp;{s.label}
                  </option>
                ))}
              </optgroup>
            ))}
            <optgroup label="Outcomes (not in the score)">
              {OUTCOME_METRICS.map((o) => (
                <option key={o.key} value={`${o.key}_pctile`}>
                  {o.label}
                </option>
              ))}
            </optgroup>
          </select>
          <div className="flex rounded border border-hairline overflow-hidden shrink-0" role="group" aria-label="Sort direction">
            <button
              onClick={() => setRankOrder('desc')}
              aria-pressed={rankOrder === 'desc'}
              className={`px-1.5 py-0.5 text-[10px] ${rankOrder === 'desc' ? 'bg-accent text-paper' : 'text-graphite hover:bg-paper'}`}
            >
              Highest
            </button>
            <button
              onClick={() => setRankOrder('asc')}
              aria-pressed={rankOrder === 'asc'}
              className={`px-1.5 py-0.5 text-[10px] border-l border-hairline ${rankOrder === 'asc' ? 'bg-accent text-paper' : 'text-graphite hover:bg-paper'}`}
            >
              Lowest
            </button>
          </div>
        </div>
        <div className="text-[10px] text-graphite">
          {end} {metricLabel(metric).toLowerCase()} · top {rows.length}
          {stateFilter ? ` · ${stateFilter}` : ''} · relative national rank
        </div>
      </div>
      <div className="overflow-y-auto flex-1">
        {rows.map((r, i) => {
          const sel = r.z === selectedZcta;
          return (
            <button
              key={r.z}
              onMouseEnter={() => hover(r.z)}
              onMouseLeave={() => hover(null)}
              onClick={() => select(r.z, { fly: true })}
              className={`w-full px-3 py-1.5 text-left border-b border-hairline/60 transition-colors ${
                sel ? 'bg-accent/10' : 'hover:bg-paper'
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="num text-[10px] text-graphite w-5 tabular-nums">{i + 1}</span>
                <span
                  className={`flex-1 truncate text-[12px] ${sel ? 'text-accent font-semibold' : 'text-ink'}`}
                  title={r.label}
                >
                  {r.label}
                </span>
                <span className="num text-[12px] text-ink font-medium w-9 text-right">{fmtRank(r.v, metric)}</span>
              </div>
              <div className="flex items-center gap-2 mt-1 pl-7">
                <span className="num text-[10px] text-graphite">{r.z}</span>
                <span className="flex-1 h-1.5 bg-hairline rounded-full overflow-hidden">
                  <span className="block h-full bg-accent/70 rounded-full" style={{ width: `${r.v}%` }} />
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
