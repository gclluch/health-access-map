import { useEffect, useRef, useState } from 'react';
import { useStore } from '../store';
import { DEFAULT_WEIGHTS, PRESETS, type Weights } from '../lib/types';

const ROWS: Array<{ key: keyof Weights; label: string }> = [
  { key: 'health_need', label: 'Health need' },
  { key: 'social_vulnerability', label: 'Social vulnerability' },
  { key: 'care_access', label: 'Barriers to care' },
];

// The standout feature, made legible (§13.5): tucked behind a disclosure, with
// presets, a reset, and a live active-weighting readout. The sliders are the
// *honest* resolution to a subjective, collinear composite (§15.7).
export default function WeightSliders() {
  const storeWeights = useStore((s) => s.weights);
  const metric = useStore((s) => s.metric);
  const setWeights = useStore((s) => s.setWeights);
  const resetWeights = useStore((s) => s.resetWeights);
  const applyPreset = useStore((s) => s.applyPreset);
  const setMetric = useStore((s) => s.setMetric);
  const empiricalWeights = useStore((s) => s.empiricalWeights);
  const empiricalFit = useStore((s) => s.empiricalFit);

  // Local mirror keeps the thumb + readout instant; commits to the store (which
  // recolors 33k polygons + re-sorts rankings) are throttled so a drag doesn't
  // fire dozens of full recomputes per second.
  const [local, setLocal] = useState<Weights>(storeWeights);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => setLocal(storeWeights), [storeWeights]); // sync preset/reset
  const commit = (w: Weights) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setWeights(w), 80);
  };
  const weights = local;

  const isDefault =
    weights.health_need === DEFAULT_WEIGHTS.health_need &&
    weights.social_vulnerability === DEFAULT_WEIGHTS.social_vulnerability &&
    weights.care_access === DEFAULT_WEIGHTS.care_access;

  return (
    <div className="px-3 py-2.5 border-t border-hairline">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[12px] font-medium text-ink">Customize the score</span>
        <button
          className="text-[11px] text-accent hover:underline disabled:text-graphite disabled:no-underline"
          onClick={resetWeights}
          disabled={isDefault}
        >
          Reset to default
        </button>
      </div>

      <div className="flex gap-1.5 mb-2 flex-wrap">
        {Object.keys(PRESETS).map((name) => (
          <button
            key={name}
            onClick={() => {
              applyPreset(name);
              if (metric !== 'access_gap_score') setMetric('access_gap_score');
            }}
            className="text-[11px] px-2 py-1 rounded border border-hairline text-graphite hover:border-accent hover:text-accent transition-colors"
          >
            {name}
          </button>
        ))}
        {empiricalWeights && (
          <button
            onClick={() => {
              setLocal(empiricalWeights);
              setWeights(empiricalWeights);
              if (metric !== 'access_gap_score') setMetric('access_gap_score');
            }}
            title={
              empiricalFit
                ? `NNLS regression on life expectancy (R²=${empiricalFit.r2_vs_life_expectancy}, n=${empiricalFit.n})`
                : 'Derived from life expectancy'
            }
            className="text-[11px] px-2 py-1 rounded border border-accent/40 text-accent hover:bg-accent/5 transition-colors"
          >
            Data-driven ✦
          </button>
        )}
      </div>
      {empiricalWeights && (
        <p className="text-[10px] text-graphite mb-2 leading-snug">
          "Data-driven" derives weights by regressing the dimensions on life expectancy - it
          loads heavily onto health need (disease predicts mortality far more than supply does
          at the area level, and is near-tautological with it). The default is the deliberate
          access-construct balance.
        </p>
      )}

      {ROWS.map(({ key, label }) => (
        <div key={key} className="mb-2">
          <div className="flex justify-between text-[11px] mb-0.5">
            <span className="text-graphite">{label}</span>
            <span className="num text-ink font-medium">{weights[key]}</span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            value={weights[key]}
            onChange={(e) => {
              const next = { ...local, [key]: Number(e.target.value) };
              setLocal(next); // instant thumb + readout
              commit(next); // throttled recompute
              if (metric !== 'access_gap_score') setMetric('access_gap_score');
            }}
            className="w-full accent-accent h-1 cursor-pointer"
            aria-label={`${label} weight`}
          />
        </div>
      ))}

      <div className="num text-[11px] text-graphite mt-1.5">
        Need {weights.health_need} · Vuln {weights.social_vulnerability} · Access{' '}
        {weights.care_access}
        <span className="ml-1 text-graphite">(normalized)</span>
      </div>
    </div>
  );
}
