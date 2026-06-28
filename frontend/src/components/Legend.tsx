import { useMemo } from 'react';
import { useStore } from '../store';
import { metricValue } from '../lib/scoring';
import { buildQuantile, quantileBreaks, QUANTILE_COLORS, CHROME } from '../lib/colors';
import { ACCESS_RESID_METRIC, COMPOSITE_METRIC, COMPOSITE_MULT_METRIC, WITHIN_STATE_METRIC } from '../lib/types';
import { fmtScore } from '../lib/format';
import Caret from './Caret';
import MetricSelect from './MetricSelect';

const BINS = 44;

const LENS_HELP: Record<string, string> = {
  [COMPOSITE_METRIC]:
    'Relative access disadvantage: where this ZIP ranks against all other U.S. ZIPs on need, vulnerability, and barriers combined - a national percentile, not need minus supply. For barriers beyond what need predicts, switch to "barriers to care, net of deprivation".',
  [COMPOSITE_MULT_METRIC]:
    'Targeting lens: emphasizes places where high need and high barriers coincide, instead of letting one dimension fully offset another.',
  [ACCESS_RESID_METRIC]:
    'Structural-access lens: barriers to care after health need + social vulnerability are statistically removed.',
  [WITHIN_STATE_METRIC]:
    'Decision-context lens: ranks each ZIP against peers in the same state, useful for state programs and grant targeting.',
};

// The signature element (§14.4): a histogram of all ZIPs along the active
// metric's axis, ramp beneath, and a marker for where the selected ZIP falls.
// The whole product is about *relative position*; the legend says it directly.
export default function Legend() {
  const { metrics, metric, weights, selectedZcta, stateFilter } = useStore();
  const setMetric = useStore((s) => s.setMetric);
  const showWeights = useStore((s) => s.showWeights);
  const toggleWeights = useStore((s) => s.toggleWeights);

  const { hist, max, selValue, selBin, breaks, noData } = useMemo(() => {
    const vals: number[] = [];
    let missing = 0;
    for (const m of metrics.values()) {
      const v = metricValue(m, metric, weights);
      if (v != null && !Number.isNaN(v)) vals.push(v);
      else missing += 1;
    }
    const h = new Array(BINS).fill(0);
    for (const v of vals) {
      const b = Math.min(BINS - 1, Math.max(0, Math.floor((v / 100) * BINS)));
      h[b] += 1;
    }
    const sel = selectedZcta ? metrics.get(selectedZcta) : undefined;
    const sv = sel ? metricValue(sel, metric, weights) : null;
    const sb = sv != null ? Math.min(BINS - 1, Math.floor((sv / 100) * BINS)) : null;
    const scale = buildQuantile(vals);
    return {
      hist: h,
      max: Math.max(1, ...h),
      selValue: sv,
      selBin: sb,
      breaks: quantileBreaks(scale),
      noData: missing,
    };
  }, [metrics, metric, weights, selectedZcta]);

  return (
    <div className="panel rounded-md px-3 py-2.5 w-full max-[520px]:py-2">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] uppercase tracking-wide text-graphite">Color by</span>
        <div className="relative max-w-[200px] max-[520px]:max-w-[210px]">
          <MetricSelect
            ariaLabel="Color the map by metric"
            className="w-full appearance-none text-[12px] bg-transparent text-ink font-medium outline-none cursor-pointer focus:ring-2 focus:ring-accent/40 rounded pr-5 text-right"
            value={metric}
            onChange={setMetric}
            includeWithinState={!!stateFilter}
          />
          <Caret
            open
            size={12}
            className="pointer-events-none absolute right-0 top-1/2 -translate-y-1/2 text-graphite"
          />
        </div>
      </div>

      {LENS_HELP[metric] && (
        <p className="text-[11px] text-graphite mb-1.5 leading-snug">
          {LENS_HELP[metric]} Colors are quantile bands: each color holds roughly the same number
          of scored ZIPs.
        </p>
      )}

      <svg
        viewBox={`0 0 ${BINS} 30`}
        preserveAspectRatio="none"
        className="w-full h-[42px] max-[520px]:h-[32px]"
        role="img"
        aria-label={
          selValue != null
            ? `Distribution of scored ZIPs; ${selectedZcta} sits at ${fmtScore(selValue)} out of 100`
            : 'Distribution of scored ZIPs along the selected metric'
        }
      >
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

      {/* stepped quantile ramp: matches the map's eight equal-count color classes. */}
      <div className="grid grid-cols-8 h-2.5 rounded-sm mt-0.5 overflow-hidden border border-hairline/60">
        {QUANTILE_COLORS.map((color, i) => (
          <span key={i} style={{ backgroundColor: color }} className={i > 0 ? 'border-l border-white/40' : ''} />
        ))}
      </div>
      <div className="relative h-3 mt-0.5" aria-hidden="true">
        {breaks.slice(1, 6).map((b, i) => (
          <span
            key={`${b}-${i}`}
            className="absolute top-0 h-1.5 border-l border-graphite/45"
            style={{ left: `${((i + 2) / 8) * 100}%` }}
            title={`Quantile break ${fmtScore(b)}`}
          />
        ))}
      </div>
      <div className="flex justify-between gap-2 text-[10px] num text-graphite -mt-1">
        <span>lower disadvantage</span>
        {selValue != null && (
          <span className="text-accent font-medium">
            {selectedZcta} · {fmtScore(selValue)}
          </span>
        )}
        <span>higher disadvantage</span>
      </div>
      <div className="mt-1 flex items-center justify-between gap-2 text-[10px] text-graphite">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-4 rounded-sm border border-hairline bg-[#CACED4]" />
          no reliable data{noData > 0 ? <span className="num"> · {noData.toLocaleString()}</span> : null}
        </span>
        <span className="num">8 quantile bands</span>
      </div>

      {/* Weighting control - sibling of the metric selector above. Expands the sliders
          upward (rendered above this panel by App). Shows the live weights at a glance.
          Hidden while the sliders are open - the WeightSliders header is then the sole
          collapse affordance (avoids two identical "Adjust weighting" toggles at once). */}
      {!showWeights && (
        <button
          onClick={toggleWeights}
          aria-expanded={showWeights}
          className="mt-2 pt-2 w-full flex items-center justify-between border-t border-hairline text-[12px] font-medium text-accent hover:text-accent-soft max-[520px]:mt-1.5 max-[520px]:pt-1.5"
        >
          <span>
            Adjust weighting
            <span className="num text-graphite font-normal">
              {' · '}{weights.health_need}/{weights.social_vulnerability}/{weights.care_access}
            </span>
          </span>
          <Caret open={showWeights} size={15} className="text-accent" />
        </button>
      )}
    </div>
  );
}
