import { useMemo } from 'react';
import { useStore } from '../store';
import { metricValue } from '../lib/scoring';
import { RAMP, CHROME } from '../lib/colors';
import { ACCESS_RESID_METRIC, COMPOSITE_METRIC, COMPOSITE_MULT_METRIC, MODEL, OUTCOME_METRICS } from '../lib/types';
import { fmtScore } from '../lib/format';

const BINS = 44;

// The signature element (§14.4): a histogram of all ZIPs along the active
// metric's axis, ramp beneath, and a marker for where the selected ZIP falls.
// The whole product is about *relative position*; the legend says it directly.
export default function Legend() {
  const { metrics, metric, weights, selectedZcta } = useStore();
  const setMetric = useStore((s) => s.setMetric);
  const showWeights = useStore((s) => s.showWeights);
  const toggleWeights = useStore((s) => s.toggleWeights);

  const { hist, max, selValue, selBin } = useMemo(() => {
    const vals: number[] = [];
    for (const m of metrics.values()) {
      const v = metricValue(m, metric, weights);
      if (v != null && !Number.isNaN(v)) vals.push(v);
    }
    const h = new Array(BINS).fill(0);
    for (const v of vals) {
      const b = Math.min(BINS - 1, Math.max(0, Math.floor((v / 100) * BINS)));
      h[b] += 1;
    }
    const sel = selectedZcta ? metrics.get(selectedZcta) : undefined;
    const sv = sel ? metricValue(sel, metric, weights) : null;
    const sb = sv != null ? Math.min(BINS - 1, Math.floor((sv / 100) * BINS)) : null;
    return { hist: h, max: Math.max(1, ...h), selValue: sv, selBin: sb };
  }, [metrics, metric, weights, selectedZcta]);

  return (
    <div className="panel rounded-md px-3 py-2.5 w-full">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] uppercase tracking-wide text-graphite">Color by</span>
        <select
          aria-label="Color the map by metric"
          className="text-[12px] bg-transparent text-ink font-medium outline-none cursor-pointer focus:ring-2 focus:ring-accent/40 rounded max-w-[200px]"
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
        >
          <option value={COMPOSITE_METRIC}>Access gap (composite)</option>
          <option value={COMPOSITE_MULT_METRIC}>Access gap (coincidence lens)</option>
          <option value={ACCESS_RESID_METRIC}>Barriers to care, net of deprivation</option>
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
      </div>

      {metric === ACCESS_RESID_METRIC && (
        <p className="text-[10px] text-graphite mb-1 leading-snug">
          Barriers to care with health need + social vulnerability statistically removed - brighter
          = access worse than this area's deprivation predicts (structural, not just "a poor area").
        </p>
      )}

      <svg viewBox={`0 0 ${BINS} 30`} preserveAspectRatio="none" className="w-full h-[42px]">
        {hist.map((c, i) => (
          <rect
            key={i}
            x={i}
            y={30 - (c / max) * 28}
            width={0.92}
            height={(c / max) * 28}
            fill={i === selBin ? CHROME.accent : CHROME.histBar}
          />
        ))}
        {selBin != null && (
          <line x1={selBin + 0.5} y1={0} x2={selBin + 0.5} y2={30} stroke={CHROME.accent} strokeWidth={0.4} />
        )}
      </svg>

      {/* ramp */}
      <div
        className="h-2 rounded-sm mt-0.5"
        style={{
          background: `linear-gradient(to right, ${Array.from({ length: 9 }, (_, i) => RAMP((i / 8) * 100)).join(',')})`,
        }}
      />
      <div className="flex justify-between text-[10px] num text-graphite mt-0.5">
        <span>low</span>
        {selValue != null && (
          <span className="text-accent font-medium">
            {selectedZcta} · {fmtScore(selValue)}
          </span>
        )}
        <span>high</span>
      </div>

      {/* Weighting control - sibling of the metric selector above. Expands the sliders
          upward (rendered above this panel by App). Shows the live weights at a glance. */}
      <button
        onClick={toggleWeights}
        aria-expanded={showWeights}
        className="mt-2 pt-1.5 w-full flex items-center justify-between border-t border-hairline text-[11px] text-accent hover:text-accent-soft"
      >
        <span>
          <span aria-hidden>⚖ </span>Adjust weighting
          <span className="num text-graphite">
            {' · '}{weights.health_need}/{weights.social_vulnerability}/{weights.care_access}
          </span>
        </span>
        <span className="text-graphite">{showWeights ? '▾' : '▸'}</span>
      </button>
    </div>
  );
}
