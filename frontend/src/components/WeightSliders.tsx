import { useEffect, useRef, useState } from 'react';
import { useStore } from '../store';
import { COMPOSITE_METRIC, COMPOSITE_MULT_METRIC, DEFAULT_WEIGHTS, PRESETS, type Weights } from '../lib/types';
import Caret from './Caret';

// Weights only change the composite metrics (additive + the geometric lens, both weight-driven).
// If the user is viewing a sub-score/outcome, snap to the additive composite so the weight change
// is visible; if they're already on either composite, leave them there (don't kick lens users off).
const ensureCompositeVisible = (metric: string, setMetric: (m: string) => void) => {
  if (metric !== COMPOSITE_METRIC && metric !== COMPOSITE_MULT_METRIC) setMetric(COMPOSITE_METRIC);
};

const ROWS: Array<{ key: keyof Weights; label: string }> = [
  { key: 'health_need', label: 'Health need' },
  { key: 'social_vulnerability', label: 'Social vulnerability' },
  { key: 'care_access', label: 'Barriers to care' },
];

// compact chip labels for the outcome-anchored presets (full label is in the tooltip)
const ANCHOR_SHORT: Record<string, string> = {
  preventable_hosp: 'Preventable hosp.',
  amenable_mortality: 'Amenable mortality',
  premature_death: 'Premature death',
  infant_mortality: 'Infant mortality',
  flu_vaccination: 'Flu vaccination',
  mammography: 'Mammography',
  life_expectancy: 'Life expectancy',
};

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
  const toggleWeights = useStore((s) => s.toggleWeights);
  const anchors = useStore((s) => s.anchors);

  // Local mirror keeps the thumb + readout instant; commits to the store (which
  // recolors 33k polygons + re-sorts rankings) are throttled so a drag doesn't
  // fire dozens of full recomputes per second.
  const [local, setLocal] = useState<Weights>(storeWeights);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => setLocal(storeWeights), [storeWeights]); // sync preset/reset
  useEffect(() => () => clearTimeout(timer.current), []); // drop pending commit on unmount
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
        <button
          onClick={toggleWeights}
          aria-expanded={true}
          aria-label="Collapse weighting"
          className="flex items-center gap-1.5 text-[12px] font-medium text-ink hover:text-accent"
        >
          <Caret open size={14} className="text-graphite" />
          Adjust weighting
        </button>
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
              ensureCompositeVisible(metric, setMetric);
            }}
            className="text-[11px] px-2 py-1 rounded border border-hairline text-graphite hover:border-accent hover:text-accent transition-colors"
          >
            {name}
          </button>
        ))}
      </div>

      {anchors.length > 0 && (
        <>
          <div className="text-[10px] uppercase tracking-wide text-graphite mb-1">
            Weight by what tracks an outcome
          </div>
          <div className="flex gap-1.5 mb-2 flex-wrap">
            {anchors.map((a) => (
              <button
                key={a.key}
                onClick={() => {
                  setLocal(a.weights);
                  setWeights(a.weights);
                  ensureCompositeVisible(metric, setMetric);
                }}
                title={
                  `${a.label} - weights ∝ each dimension's correlation with this outcome` +
                  (a.fit ? ` (model R²=${a.fit.r2}, n=${a.fit.n}).` : '.') +
                  ` ${a.caveat}`
                }
                className={
                  'text-[11px] px-2 py-1 rounded border transition-colors ' +
                  (a.key === 'life_expectancy'
                    ? 'border-hairline text-graphite hover:border-graphite'
                    : 'border-accent/40 text-accent hover:bg-accent/5')
                }
              >
                {ANCHOR_SHORT[a.key] ?? a.label}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-graphite mb-2 leading-snug">
            These weight each dimension by how strongly it tracks an independent outcome (CMS/NCHS
            records, not PLACES). Care access stays modest everywhere - area outcomes are
            disease-dominated - so the default keeps it by deliberate choice, not regression.
            Life expectancy is a need outcome (a validity check, not a recommended weighting).
          </p>
        </>
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
              ensureCompositeVisible(metric, setMetric);
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

      <p className="text-[10px] text-graphite mt-2 leading-snug border-t border-hairline pt-2">
        <span className="text-ink font-medium">A sensitivity probe, not a rewrite.</span> The three
        dimensions are strongly correlated (~1.6 effective dimensions), so even large weight
        changes move a ZIP's national rank only ~±6 points (Spearman ~0.999). Use this to see what
        the score is sensitive to - not to hunt for a "true" weighting that doesn't exist.
      </p>
    </div>
  );
}
