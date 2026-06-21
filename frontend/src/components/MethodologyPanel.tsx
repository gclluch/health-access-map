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
    'Supply uses E2SFCA (Luo & Qi 2009) - a floating catchment with Gaussian distance decay, so a clinic 2 km away counts far more than one at the 16 km edge. This fixes the ZIP-containment artifact. It is still a relative spatial-access measure over NPPES registrations (which over-count active capacity and ignore Medicaid/new-patient acceptance). A need-adjusted variant is computed but not scored (it would double-count health need). The HRSA 3,500:1 flag is the one benchmark-referenced gap.',
  ],
  [
    'Collinear, weighted dimensions',
    'Health need, social vulnerability, and care access are correlated (~0.5), so the weighted sum double-counts shared variance. The tunable weights make that subjectivity explicit rather than hidden.',
  ],
  [
    'Small-area noise',
    'Low-population ZIPs have wide margins of error; they are flagged low-confidence and excluded from the headline rankings. Uninhabited/data-starved ZIPs render gray ("no reliable data").',
  ],
  [
    'Why social vulnerability is access, not a descriptor',
    'Access ≠ supply. A provider you can\'t afford, reach, or communicate with isn\'t accessible. Per the 5 A\'s of access (Penchansky & Thomas) and Andersen\'s enabling factors, affordability (income), accessibility (transportation), and acceptability (language) are dimensions of access. The federal Medically Underserved formula itself uses % poverty + % elderly alongside provider supply. Proof it isn\'t just a descriptor: we DO have descriptors (age, % minority) and score them zero.',
  ],
  [
    'Why these weights (35 / 30 / 35), and the data-driven alternative',
    'The default is a conceptual value judgment (as in County Health Rankings) - need and barriers to care, the two sides of the gap, sit slightly above vulnerability; all near-equal. The "Data-driven" preset derives weights empirically (Healthy Places Index method: NNLS regression of the dimensions on CDC life expectancy) and comes out ~76% health need / 20% vulnerability / 5% access. That\'s a real finding - at the area level disease burden predicts mortality far more than provider supply does (also partly tautological: disease ≈ death). It nearly zeroes out access, which is why an access tool keeps access by deliberate choice. The sliders let you pick.',
  ],
  [
    'Outcomes layer (independent of the score)',
    'Life expectancy at birth (CDC USALEEP, from death records - the one input NOT derived from BRFSS/PLACES) is shown as a separate outcome and used to derive the empirical weights. It is NOT in the access-gap composite (outcomes are the result, not a driver - the County Health Rankings stance). The composite also correlates ~0.85 with PLACES fair/poor health as a sanity anchor.',
  ],
  [
    'Different vintages & universes',
    'NPPES (this month), ACS 5-year (centered ~2-3 yrs back), and PLACES (a BRFSS year) describe different times and populations (adults 18+, civilian noninstitutionalized, total). See provenance.json.',
  ],
];

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
            ACS roll up into 11 sub-scores, then 3 dimensions (health need, social vulnerability,
            care access), then one 0-100 relative national rank. Darker = higher gap. Tap any layer
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
                <b>Sub-scores</b> (11) = the average of their member percentiles, re-ranked. E.g.
                "unmet social needs" averages food, housing, transport &amp; utility insecurity.
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
