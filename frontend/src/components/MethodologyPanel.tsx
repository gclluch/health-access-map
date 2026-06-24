import { useEffect, useRef } from 'react';
import { useStore } from '../store';

// Limitations made first-class (§15.9): integrity hidden is integrity absent.
const POINTS: Array<[string, string]> = [
  [
    'Relative, not absolute',
    'A score of 95 means "worse access than 95% of U.S. ZIPs," not "objectively bad." A top-decile ZIP can still be fine in absolute terms.',
  ],
  [
    'Modeled disease estimates',
    'CDC PLACES prevalence comes from a model partly conditioned on socioeconomic structure - so the disease/poverty correlation partly recovers the model\'s own assumptions, not two independent measurements.',
  ],
    [
    'Provider supply: spatial access, not capacity',
    'Supply uses E2SFCA (Luo & Qi 2009) with a VARIABLE catchment (McGrail & Humphreys 2009): each ZIP\'s bandwidth scales with local settlement density - small in cities, wide in sparse rural areas. This removes the urbanicity artifact of a single fixed radius and roughly doubled supply\'s correlation with independent mortality (e.g. it now tracks life expectancy, which it did not under a fixed 16 km radius). It is still a relative measure over NPPES registrations (which over-count active capacity and ignore Medicaid acceptance); we tested capacity-weighting by Medicare claims volume and it did not help, so it is not used. The HRSA 3,500:1 shortage flag is computed from a fixed 16 km service area (the interpretable benchmark).',
  ],
  [
    'Collinear, weighted dimensions',
    'Health need, social vulnerability, and care access are correlated (~0.5), so the weighted sum double-counts shared variance. The tunable weights make that subjectivity explicit rather than hidden.',
  ],
  [
    'Small-area noise (and what we do about it)',
    'Low-population ZIPs have wide ACS margins of error. We apply empirical-Bayes (Fay-Herriot) shrinkage to the social/economic rates - each ZIP is pulled toward its county mean in proportion to its own noise, so a tiny, uncertain ZIP borrows strength from its county while a well-measured one keeps its own value. This improves agreement with independent outcomes. The noisiest ZIPs are still flagged low-confidence and kept out of the headline rankings; uninhabited/data-starved ZIPs render gray.',
  ],
  [
    'Can you compare two ZIPs? Only coarsely',
    'Internally the score is reliable (split-half reliability 0.95) and it tracks independent outcomes - but a ZIP\'s national rank moves ~±6 points under any reasonable re-weighting and ~±4 more from measurement noise. So two ZIPs are reliably different only if they differ by ~10-15 percentile points - about 7-10 distinct tiers, not 33,000 ranks. Each ZIP shows a "reliable range"; if two ranges overlap, treat the ZIPs as indistinguishable. No federal index (ADI, SVI, County Health Rankings) publishes this - they show point ranks the data cannot support.',
  ],
  [
    'Why social vulnerability is access, not a descriptor',
    'Access ≠ supply. A provider you can\'t afford, reach, or communicate with isn\'t accessible. Per the 5 A\'s of access (Penchansky & Thomas) and Andersen\'s enabling factors, affordability (income), accessibility (transportation), and acceptability (language) are dimensions of access. The federal Medically Underserved formula itself uses % poverty + % elderly alongside provider supply. Proof it isn\'t just a descriptor: we DO have descriptors (age, % minority) and score them zero.',
  ],
  [
    'Why these weights (35 / 30 / 35), and the outcome-anchored alternatives',
    'The default is a conceptual value judgment (as in County Health Rankings) - need and barriers to care, the two sides of the gap, sit slightly above vulnerability; all near-equal. Care access is kept meaningful by deliberate choice because it is the actionable lever - exactly as County Health Rankings weights clinical care at 20% even though it predicts less outcome variance than social factors. The "Weight by what tracks an outcome" presets are an empirical alternative: each weights the dimensions by how strongly they correlate with an independent outcome. Across every outcome and method, care access lands modest (it is collinear with need, and area outcomes are disease-dominated) - that is a real finding about outcomes, not proof access is irrelevant.',
  ],
  [
    'Outcomes layer (independent of the score, used only to validate it)',
    'Independent outcomes (from CMS claims + NCHS vital records, NOT BRFSS/PLACES) validate - never build - the composite: the four we trust are preventable (ACSC) hospitalizations, premature death, infant mortality, and life expectancy. Flu vaccination and mammography are also tracked, but treated cautiously - they double as healthcare-engagement measures, so judging access inputs against them would be circular. We also run a sub-county gate (NY ZIP-level ACSC + national life expectancy, county fixed-effects) because ~25% of the index varies within counties, invisible to county-level outcomes. Outcomes are shown as separate layers, never in the composite (the County Health Rankings stance). After the variable-catchment fix, spatial provider supply now tracks the mortality outcomes, correctly signed (it was ~uncorrelated with life expectancy under the old fixed radius).',
  ],
  [
    'Different vintages & universes',
    'NPPES (this month), ACS 5-year (centered ~2-3 yrs back), and PLACES (a BRFSS year) describe different times and populations (adults 18+, civilian noninstitutionalized, total). See provenance.json.',
  ],
];

// Live multi-anchor validation, straight from weights.json (pipeline/validate.py). Shows
// the correlation-based preset weights per outcome + how the regression collapses care
// access - the honest, in-product version of docs/VALIDATION.md.
function ValidationTable() {
  const anchors = useStore((s) => s.anchors);
  const subCorr = useStore((s) => s.subscoreCorrelations);
  if (anchors.length === 0) return null;
  const careRows: Array<[string, string]> = [
    ['provider_supply', 'Provider supply'],
    ['insurance', 'Insurance'],
    ['safetynet_access', 'Safety-net (FQHC)'],
  ];
  const fmt = (n: number | null | undefined) => (n == null ? '–' : n.toFixed(2));
  return (
    <div className="mb-4 rounded border border-hairline bg-paper/60 px-3 py-2.5">
      <div className="text-[11px] uppercase tracking-wide text-graphite mb-1.5">
        Validation against independent outcomes
      </div>
      <table className="w-full text-[11px] num">
        <thead>
          <tr className="text-graphite text-left">
            <th className="font-normal py-0.5">Outcome</th>
            <th className="font-normal text-right">Need</th>
            <th className="font-normal text-right">Vuln</th>
            <th className="font-normal text-right">Access</th>
            <th className="font-normal text-right">R²</th>
          </tr>
        </thead>
        <tbody className="text-ink">
          {anchors.map((a) => (
            <tr key={a.key} className="border-t border-hairline/60">
              <td className="py-0.5 pr-1">{a.label}</td>
              <td className="text-right">{a.weights.health_need}</td>
              <td className="text-right">{a.weights.social_vulnerability}</td>
              <td className="text-right font-medium">{a.weights.care_access}</td>
              <td className="text-right text-graphite">{a.fit ? a.fit.r2 : '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[10px] text-graphite mt-2 leading-snug">
        Weights ∝ each dimension's correlation with the outcome. A pure regression instead
        loads ~75-90% onto health need and floors access at ~5% - because the dimensions are
        collinear and area outcomes are disease-dominated, not because access doesn't matter.
      </p>
      <div className="text-[10px] text-graphite mt-2 leading-snug">
        <span className="uppercase tracking-wide">Care sub-scores, signed correlation</span>
        <table className="w-full num mt-1">
          <thead>
            <tr className="text-left">
              <th className="font-normal" />
              {anchors.map((a) => (
                <th key={a.key} className="font-normal text-right">{a.key.split('_')[0]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {careRows.map(([key, label]) => (
              <tr key={key}>
                <td className="pr-1 text-ink">{label}</td>
                {anchors.map((a) => {
                  const r = subCorr[a.key]?.[key];
                  return (
                    <td key={a.key} className={'text-right ' + (r != null && r < 0 ? 'text-rose-500' : '')}>
                      {fmt(r)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 leading-snug">
          Provider supply tracks infant mortality (+) but is ~0 vs life expectancy; safety-net
          (FQHC) reads wrong-signed (red) - clinics sit in the highest-need areas, and it is
          wrong-signed <i>within</i> counties in 85% of states, so it is now shown for context
          but <b>excluded from the composite</b> (computed + displayed, not scored).
        </p>
      </div>
    </div>
  );
}

export default function MethodologyPanel() {
  const show = useStore((s) => s.showMethodology);
  const toggle = useStore((s) => s.toggleMethodology);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const restoreRef = useRef<Element | null>(null);

  useEffect(() => {
    if (!show) return;
    restoreRef.current = document.activeElement;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') toggle(false);
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      (restoreRef.current as HTMLElement | null)?.focus?.();
    };
  }, [show, toggle]);

  if (!show) return null;
  return (
    <div
      className="fixed inset-0 z-50 bg-ink/30 flex items-center justify-center p-4"
      onClick={() => toggle(false)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="methodology-title"
        className="panel rounded-md max-w-[560px] w-full max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 pt-4 pb-3 border-b border-hairline flex justify-between items-start">
          <div>
            <h2 id="methodology-title" className="font-serif text-[20px] text-ink leading-tight">How to read this</h2>
            <p className="text-[12px] text-graphite mt-0.5">
              What the Access Gap Score is - and why it could mislead.
            </p>
          </div>
          <button
            ref={closeRef}
            onClick={() => toggle(false)}
            aria-label="Close"
            className="text-graphite hover:text-ink rounded focus:outline-none focus:ring-2 focus:ring-accent/40"
          >
            ✕
          </button>
        </div>
        <div className="px-5 py-4">
          <p className="text-[13px] text-ink leading-relaxed mb-3">
            The Access Gap Score is a hierarchy: ≈50 measures from CDC PLACES, CMS NPPES, and Census
            ACS roll up into 11 sub-scores (10 scored), then 3 dimensions (health need, social
            vulnerability, care access), then one 0-100 relative national rank. Brighter yellow = higher gap; deep
            blue = lower (cividis, colorblind-safe). Tap any layer
            in the detail panel to drill down to the underlying measures.
          </p>

          {/* Exact formulas, in-product, so the score is never a black box. */}
          <div className="mb-4 rounded border border-hairline bg-paper/60 px-3 py-2.5">
            <div className="text-[11px] uppercase tracking-wide text-graphite mb-1.5">
              How the score is built
            </div>
            <ul className="text-[12px] text-ink leading-relaxed space-y-1.5">
              <li>
                <b>Every measure</b> (≈50 of them) is oriented so higher = worse, then{' '}
                <b>percentile-ranked nationally</b> (0-100). This is the CDC SVI method - ordinal
                ranking is robust to skew and outliers.
              </li>
              <li>
                <b>Sub-scores</b> (11, of which 10 are scored) = the average of their member
                percentiles, re-ranked. E.g. "unmet social needs" averages food, housing, transport
                &amp; utility insecurity. (The FQHC safety-net sub-score is shown but unscored - it is
                wrong-signed within counties.)
              </li>
              <li>
                <b>Dimensions</b> (3) = the average of their sub-scores, re-ranked:{' '}
                <span className="num">health need</span>, <span className="num">social
                vulnerability</span>, <span className="num">care access</span>.
              </li>
              <li className="pt-1 border-t border-hairline">
                <b>Access gap</b> ={' '}
                <span className="num">0.35·need + 0.30·vulnerability + 0.35·access</span> - a{' '}
                <i>relative composite index</i>, re-ranked so "worse than X%" is a true percentile.
                Weights re-tunable with the sliders.
              </li>
            </ul>
            <p className="text-[11px] text-graphite mt-2">
              Dimensions are correlated (~0.5), so the weighted sum partly double-counts shared
              variance - the sliders exist precisely so that judgment is yours, not hidden.
            </p>
          </div>
          <ValidationTable />
          {POINTS.map(([title, body]) => (
            <div key={title} className="mb-3">
              <div className="text-[13px] font-medium text-ink">{title}</div>
              <div className="text-[12px] text-graphite leading-snug mt-0.5">{body}</div>
            </div>
          ))}
          <div className="border-t border-hairline pt-3">
            <div className="text-[11px] uppercase tracking-wide text-graphite mb-1">
              Sources &amp; vintages
            </div>
            <p className="text-[11px] text-graphite leading-snug">
              Disease: CDC PLACES ZCTA, 2025 release (BRFSS). Providers: CMS NPPES monthly full
              file. Economics: Census ACS 5-year, 2023. Geography: Census TIGER 2020 ZCTA + ZCTA→county
              relationship. These describe <i>different time points</i> - a registry snapshot, a
              5-year average centered ~2-3 years back, and a survey year - so trends across layers
              should be read with that skew in mind.
            </p>
          </div>
          <p className="text-[11px] text-graphite border-t border-hairline pt-3 mt-3">
            Area patterns are not individual-level facts (ecological fallacy). Crude prevalence
            reflects age mix. This is an exploratory instrument, not a clinical or policy verdict.
          </p>
        </div>
      </div>
    </div>
  );
}
