import { useState } from 'react';
import { dimensionContributions } from '../lib/scoring';
import { fmtScore, ordinal } from '../lib/format';
import { DEFAULT_WEIGHTS, type SlimMetric, type Weights } from '../lib/types';

const DIMS = [
  ['health_need', 'Health need'],
  ['social_vulnerability', 'Social vulnerability'],
  ['care_access', 'Barriers to care'],
] as const;
// driver-rank shades (biggest driver darkest), reused for the bar + legend dot + severity fill.
// Kept dark enough that the white share-% label stays legible on the lightest segment (a11y).
const SHADES = ['bg-accent', 'bg-accent/80', 'bg-accent/60'];

// "What drives the score": a 100%-stacked driver-share bar (each segment = that dimension's SHARE
// of the score, summing to 100% - the attribution view) above a key listing all dimensions. At
// rest the key shows only share + severity numbers; hovering/focusing a segment or row expands
// that dimension's SEVERITY bar (national percentile, 0-100) plus its weight - so the default view
// answers "what drives this" and the hover answers "how bad is it, and why it counts."
export default function DriversSection({
  m,
  weights,
  score,
  scorePercentile,
}: {
  m: SlimMetric;
  weights: Weights;
  score: number | null;
  scorePercentile: number | null;
}) {
  const contrib = dimensionContributions(m, weights);
  const [active, setActive] = useState(-1); // -1 = nothing hovered: key only, no expanded bar
  if (!contrib || score == null) return null;

  const wsum = weights.health_need + weights.social_vulnerability + weights.care_access || 1;
  const presentDims = DIMS.map(([key, label]) => ({
    key,
    label,
    pct: m[`${key}_pctile`] as number | null,
    c: contrib[key],
  })).filter((r) => r.pct != null);
  if (!presentDims.length) return null;

  // Per-row weight % is renormalized over the dimensions actually present for this ZIP, so it
  // shares a denominator with the driver shares below (both sum to 100% on a 2-of-3-dim ZIP).
  const presentWsum = presentDims.reduce((a, r) => a + weights[r.key], 0) || 1;
  const present = presentDims.map((r) => ({ ...r, wpct: Math.round((weights[r.key] / presentWsum) * 100) }));

  const total = present.reduce((a, r) => a + r.c, 0) || 1;
  const rows = present
    .sort((a, b) => b.c - a.c)
    .map((r, i) => ({ ...r, shade: SHADES[i] ?? 'bg-accent/50', share: (r.c / total) * 100 }));

  const isDefault =
    weights.health_need === DEFAULT_WEIGHTS.health_need &&
    weights.social_vulnerability === DEFAULT_WEIGHTS.social_vulnerability &&
    weights.care_access === DEFAULT_WEIGHTS.care_access;
  const pctOf = (w: number) => Math.round((w / wsum) * 100);

  return (
    <div className="mt-3 pt-2.5 border-t border-hairline">
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-[12px] uppercase tracking-wide text-graphite">What drives the score</span>
        <span className="text-[11px] text-graphite">share of the score · hover for detail</span>
      </div>

      {/* attribution: 100%-stacked driver-share bar */}
      <div
        className="flex h-6 rounded overflow-hidden border border-hairline"
        role="group"
        aria-label="What drives the score - share by dimension"
      >
        {rows.map((r, i) => (
          <button
            key={r.key}
            type="button"
            onMouseEnter={() => setActive(i)}
            onFocus={() => setActive(i)}
            onMouseLeave={() => setActive(-1)}
            onBlur={() => setActive(-1)}
            aria-label={`${r.label}: drives ${Math.round(r.share)}% of the score, ${ordinal(
              r.pct,
            )} percentile severity, weight ${r.wpct}%`}
            className={`relative grid place-items-center ${r.shade} ${
              i === active ? 'ring-1 ring-inset ring-ink/40' : ''
            }`}
            style={{ width: `${r.share}%` }}
          >
            {r.share >= 13 && (
              <span className="num text-[11px] text-paper font-medium leading-none">{Math.round(r.share)}%</span>
            )}
          </button>
        ))}
      </div>

      {/* key: every dimension is always listed (dot + name + share + severity). The hovered/
          focused row expands to its severity bar + weight; at rest none is expanded. */}
      <div className="mt-1.5">
        {rows.map((r, i) => {
          const on = i === active;
          return (
            <button
              key={r.key}
              type="button"
              onMouseEnter={() => setActive(i)}
              onFocus={() => setActive(i)}
              onMouseLeave={() => setActive(-1)}
              onBlur={() => setActive(-1)}
              aria-label={`${r.label}: drives ${Math.round(r.share)}% of the score, ${ordinal(
                r.pct,
              )} percentile severity, weight ${r.wpct}%`}
              className={`w-full text-left px-1 py-1 rounded ${on ? 'bg-paper' : 'hover:bg-paper/60'}`}
            >
              <div className="flex items-baseline gap-2">
                <span className={`inline-block w-2 h-2 rounded-sm shrink-0 ${r.shade}`} />
                <span className="text-[12px] text-ink flex-1 truncate">{r.label}</span>
                <span className="num text-[11px] text-graphite">drives {Math.round(r.share)}%</span>
                <span className="num text-[12px] text-ink font-medium w-9 text-right">{ordinal(r.pct)}</span>
              </div>
              {on && (
                <div className="pl-4 pr-1 mt-0.5">
                  <div className="h-2 bg-hairline rounded-full overflow-hidden">
                    <span className={`block h-full rounded-full ${r.shade}`} style={{ width: `${r.pct}%` }} />
                  </div>
                  <div className="num text-[10px] text-graphite mt-0.5">
                    severity {ordinal(r.pct)} pctile · weight {r.wpct}%
                  </div>
                </div>
              )}
            </button>
          );
        })}
      </div>

      <div className="text-[11px] text-graphite mt-2 leading-snug">
        Segment width = how much each dimension <span className="text-ink">drives</span> this score
        (its share); hover a segment for that dimension's <span className="text-ink">severity</span>{' '}
        (national percentile) and weight. Under {isDefault ? 'the default' : 'your'} mix (
        <span className="num">
          Need {pctOf(weights.health_need)} · Vuln {pctOf(weights.social_vulnerability)} · Access{' '}
          {pctOf(weights.care_access)}
        </span>
        ), the three dimensions combine to this ZIP's national composite rank of{' '}
        <span className="num">{fmtScore(scorePercentile)}</span>/100 (the "National" figure above).
        Re-tune under <span className="text-ink">"Adjust weighting"</span> - but the dimensions are
        strongly correlated (~1.6 effective dimensions), so the rank usually shifts only a few points.
      </div>
    </div>
  );
}
