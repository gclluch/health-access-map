import { useEffect, useMemo, useState } from 'react';
import { useStore } from '../store';
import { accessGap, accessGapMult, buildScoreIndex, percentileOf } from '../lib/scoring';
import { synthesize } from '../lib/synthesis';
import {
  MODEL, SUBSCORE_EVIDENCE, COMPOSITE_MULT_METRIC, ACCESS_RESID_METRIC, WITHIN_STATE_METRIC,
  type DimSpec, type SlimMetric,
} from '../lib/types';
import DriversSection from './DriversSection';
import { SUBSCORE_MEASURES, SUBSCORE_BLURB, fmtMeasure } from '../lib/measures';
import { apiZcta } from '../lib/api';
import { fmtInt, fmtScore, ordinal, severity } from '../lib/format';
import Tip from './Tip';
import Caret from './Caret';

// A percentile bar (0-100). Higher = worse (more disadvantage), so more fill = worse.
function PctBar({ pct }: { pct: number | null | undefined }) {
  if (pct == null) return <div className="h-1.5 bg-hairline rounded-full" />;
  return (
    <div className="h-1.5 bg-hairline rounded-full overflow-hidden">
      <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
    </div>
  );
}

function ResolutionBadge({ subKey }: { subKey: string }) {
  const meta = SUBSCORE_EVIDENCE[subKey];
  if (!meta) return null;
  const isCounty = meta.kind === 'county';
  const isContext = meta.kind === 'context';
  return (
    <Tip
      tip={meta.tip}
      focusable={false}
      className={
        'shrink-0 rounded border px-1 py-0.5 text-[9px] uppercase tracking-wide cursor-help ' +
        (isCounty
          ? 'border-accent/30 bg-accent/8 text-accent'
          : isContext
            ? 'border-hairline bg-paper text-graphite'
            : 'border-hairline bg-surface text-graphite')
      }
    >
      {meta.label}
    </Tip>
  );
}

// Deepest level: individual measures for a sub-score, from the full API record.
// Each row shows the RAW value (real-world units) and, where it exists, that value's
// national percentile oriented so higher = worse access (same scale as the sub-scores).
function Measures({
  subKey,
  rec,
  recLoading,
}: {
  subKey: string;
  rec: Record<string, unknown> | null;
  recLoading: boolean;
}) {
  const measures = SUBSCORE_MEASURES[subKey] ?? [];
  if (!rec)
    return (
      <div className="px-3 py-1.5 text-[10px] text-graphite">
        {recLoading ? 'Loading measures…' : 'Detailed measures are unavailable for this ZIP.'}
      </div>
    );
  const anyPct = measures.some((mm) => typeof rec[`${mm.col}_natpct`] === 'number');
  return (
    <div className="px-3 py-1.5 bg-paper/60">
      <div className="flex justify-between text-[10px] uppercase tracking-wide text-graphite pb-1 border-b border-hairline/60 mb-0.5">
        <span>Measure</span>
        <span>{anyPct ? 'value · natl %ile' : 'value'}</span>
      </div>
      {measures.map((mm) => {
        const natpct = rec[`${mm.col}_natpct`];
        const hasPct = typeof natpct === 'number';
        const tip = `${mm.label}${mm.desc ? ` - ${mm.desc}` : ''}${
          hasPct
            ? ` · This area ranks ${ordinal(Math.round(natpct as number))} nationally (higher = worse access).`
            : ''
        }`;
        return (
          <Tip
            key={mm.col}
            tip={tip}
            className="flex justify-between items-baseline text-[11px] py-0.5 cursor-help"
          >
            <span className="text-graphite truncate pr-2 flex-1">
              {mm.label}
              {mm.desc ? <span className="text-graphite"> ⓘ</span> : null}
            </span>
            <span className="flex items-baseline gap-1.5 shrink-0">
              <span className="num text-ink">{fmtMeasure(rec[mm.col], mm.unit)}</span>
              {hasPct ? (
                <span className="num text-[10px] text-graphite tabular-nums w-9 text-right">
                  {ordinal(Math.round(natpct as number))}
                </span>
              ) : null}
            </span>
          </Tip>
        );
      })}
    </div>
  );
}

function SubScoreRow({
  subKey,
  label,
  pct,
  rec,
  recLoading,
  scored = true,
}: {
  subKey: string;
  label: string;
  pct: number | null | undefined;
  rec: Record<string, unknown> | null;
  recLoading: boolean;
  scored?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const resolution = SUBSCORE_EVIDENCE[subKey];
  const tip =
    `${label}${SUBSCORE_BLURB[subKey] ? ` - ${SUBSCORE_BLURB[subKey]}` : ''}` +
    (resolution ? ` ${resolution.tip}` : '') +
    (scored ? '' : ' Shown for context, not scored.');
  return (
    <div className="border-t border-hairline/60">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-paper"
        aria-expanded={open}
        aria-label={`${label}. ${tip}`}
      >
        <Caret open={open} size={12} className="text-graphite" />
        <Tip
          className="flex-1 min-w-0 cursor-help"
          tip={tip}
          focusable={false}
        >
          <span className="block text-[12px] text-ink truncate">
            {label}
            {!scored && <span className="ml-1 text-[10px] text-graphite font-normal">· not scored</span>}
          </span>
        </Tip>
        <ResolutionBadge subKey={subKey} />
        <span className="num text-[10px] text-graphite w-14 text-right">
          {pct == null ? 'no data' : `${ordinal(pct)} pct`}
        </span>
        <span className="w-16">
          <PctBar pct={pct} />
        </span>
      </button>
      {open && <Measures subKey={subKey} rec={rec} recLoading={recLoading} />}
    </div>
  );
}

function Dimension({
  dim,
  m,
  rec,
  recLoading,
}: {
  dim: DimSpec;
  m: SlimMetric;
  rec: Record<string, unknown> | null;
  recLoading: boolean;
}) {
  const [open, setOpen] = useState(false);
  const dimPct = m[`${dim.key}_pctile`] as number | null;
  return (
    <div className="mt-2 border border-hairline rounded-md overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left bg-surface hover:bg-paper"
        aria-expanded={open}
      >
        <Caret open={open} size={13} className="text-graphite" />
        <span className="flex-1 text-[12px] font-medium text-ink">{dim.label}</span>
        <span className="num text-[13px] font-semibold text-ink w-7 text-right">
          {fmtScore(dimPct)}
        </span>
        <span className="w-20">
          <PctBar pct={dimPct} />
        </span>
      </button>
      {open && (
        <div>
          <div className="px-3 py-1 text-[10px] text-graphite">{dim.blurb}</div>
          {dim.subs.map((s) => (
            <SubScoreRow
              key={s.key}
              subKey={s.key}
              label={s.label}
              scored={s.scored !== false}
              pct={m[`${s.key}_pctile`] as number | null}
              rec={rec}
              recLoading={recLoading}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ComparisonFrame({
  m,
  scorePercentile,
}: {
  m: SlimMetric;
  scorePercentile: number | null;
}) {
  if (scorePercentile == null) return null;
  const range =
    m.access_gap_rank_lo != null && m.access_gap_rank_hi != null
      ? `${Math.round(m.access_gap_rank_lo)}-${Math.round(m.access_gap_rank_hi)}`
      : null;
  const cells = [
    {
      label: 'National',
      value: ordinal(scorePercentile),
      detail: `tier ${Math.min(10, Math.max(1, Math.ceil(scorePercentile / 10)))} of 10; worse than ${fmtScore(Math.min(99, scorePercentile))}% of U.S. ZIPs under current weights`,
    },
    m.access_gap_pctile_within_state != null
      ? {
          label: 'Within state',
          value: ordinal(m.access_gap_pctile_within_state),
          detail: 'default-weight rank among ZIPs in this state',
        }
      : null,
    range
      ? {
          label: 'Reliable range',
          value: range,
          detail: 'overlap means two ZIPs are not clearly different',
        }
      : null,
    m.care_access_resid_pctile != null
      ? {
          label: 'Access net of deprivation',
          value: ordinal(m.care_access_resid_pctile),
          detail: 'barriers worse than need + vulnerability predict',
        }
      : null,
  ].filter((x): x is { label: string; value: string; detail: string } => x != null);

  return (
    <div className="mt-2 grid grid-cols-2 gap-1.5">
      {cells.map((c) => (
        <Tip
          key={c.label}
          tip={c.detail}
          className="rounded border border-hairline bg-paper/70 px-2.5 py-2 cursor-help"
        >
          <div className="text-[10px] uppercase tracking-wide text-graphite">{c.label}</div>
          <div className="num text-[14px] font-semibold text-ink">{c.value}</div>
          <div className="text-[11px] text-graphite leading-tight">{c.detail}</div>
        </Tip>
      ))}
    </div>
  );
}

// Demographics shown purely as context for "who lives here" - independent of the
// access-disadvantage score. Every value comes from the full API record (Census ACS 5-year),
// except population which is already in the slim metric. Cells with no data are dropped.
function WhoLivesHere({ m, rec }: { m: SlimMetric; rec: Record<string, unknown> | null }) {
  const [open, setOpen] = useState(false);
  const num = (v: unknown) => (typeof v === 'number' && !Number.isNaN(v) ? v : null);
  const pct = (v: unknown) => {
    const n = num(v);
    return n == null ? null : `${Math.round(n * 100)}%`;
  };
  const cells: Array<{ label: string; value: string; tip?: string; scored?: boolean }> = [];
  const pop = num(m.population);
  if (pop != null) cells.push({ label: 'Population', value: fmtInt(pop) });
  const age = num(rec?.median_age);
  if (age != null) cells.push({ label: 'Median age', value: String(Math.round(age)) });
  const under18 = pct(rec?.age17_rate);
  if (under18) cells.push({ label: 'Under 18', value: under18 });
  const over65 = pct(rec?.age65_rate);
  if (over65) cells.push({ label: '65 and older', value: over65 });
  const income = num(rec?.median_income);
  if (income != null)
    cells.push({
      label: 'Median income',
      value: `$${Math.round(income).toLocaleString('en-US')}`,
      scored: true,
      tip: 'Median household income. Census ACS 5-year (B19013). This is the one field here that also feeds the access-disadvantage score (socioeconomic sub-score) - everything else is context only.',
    });
  const medicaid = pct(rec?.medicaid_rate);
  if (medicaid)
    cells.push({
      label: 'Medicaid',
      value: medicaid,
      tip: 'Share on Medicaid/CHIP. Census ACS 5-year (C27007). Context only - not scored.',
    });
  const lep = pct(rec?.limited_english_rate);
  if (lep)
    cells.push({
      label: 'Limited English',
      value: lep,
      tip: 'Households where no one 14+ speaks English "very well." Census ACS 5-year (C16002).',
    });
  // Minority = 1 - non-Hispanic White. Placed last (bottom-right) so it sits directly above the
  // race breakdown it summarizes. Derived from the RAW White share when available so it ties out
  // with that breakdown; falls back to the (shrunk) pct_minority otherwise.
  const white = num(rec?.pct_white);
  const minority = white != null ? `${Math.round((1 - white) * 100)}%` : pct(rec?.pct_minority);
  if (minority)
    cells.push({
      label: 'Minority',
      value: minority,
      tip: 'Share who are not non-Hispanic White (the total of the race breakdown below). Census ACS 5-year (B03002).',
    });

  // Race & ethnicity composition (Census ACS B03002) - non-Hispanic single-race buckets plus
  // Hispanic (any race); "Other" rolls up AIAN/NHPI/some-other/two-or-more. Sorted by share.
  const raceCols: Array<[string, string]> = [
    ['pct_white', 'White'],
    ['pct_black', 'Black'],
    ['pct_hispanic', 'Hispanic'],
    ['pct_asian', 'Asian'],
    ['pct_other_race', 'Other'],
  ];
  const race: Array<{ label: string; share: number }> = [];
  for (const [col, label] of raceCols) {
    const share = num(rec?.[col]);
    if (share != null && share > 0) race.push({ label, share });
  }
  race.sort((a, b) => b.share - a.share);

  if (cells.length === 0) return null;
  return (
    <div className="mt-3 rounded-md border border-hairline bg-paper/60 px-3 py-2">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-graphite"
      >
        <Caret open={open} size={12} className="text-graphite" />
        <span>Who lives here</span>
        <span className="text-graphite normal-case">· context · only income (†) feeds the score</span>
      </button>
      {open && (
        <>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 mt-1.5">
        {cells.map((c) =>
          c.tip ? (
            <Tip
              key={c.label}
              tip={c.tip}
            className="flex justify-between items-baseline text-[12px] cursor-help"
            >
              <span className="text-graphite">
                {c.label}
                {c.scored ? <span className="text-graphite"> †</span> : null}
                <span className="text-graphite"> ⓘ</span>
              </span>
              <span className="num text-ink">{c.value}</span>
            </Tip>
          ) : (
            <div key={c.label} className="flex justify-between items-baseline text-[12px]">
              <span className="text-graphite">{c.label}</span>
              <span className="num text-ink">{c.value}</span>
            </div>
          ),
        )}
      </div>
      {race.length > 0 && (
        <div className="mt-2 pt-2 border-t border-hairline/60">
          <Tip
            className="text-[11px] uppercase tracking-wide text-graphite mb-1 cursor-help inline-block"
            tip='Race & ethnicity. Non-Hispanic single-race for White/Black/Asian; Hispanic is any race; "Other" combines American Indian/Alaska Native, Native Hawaiian/Pacific Islander, some-other-race and two-or-more. Census ACS 5-year (B03002). Context only - not scored.'
          >
            Race &amp; ethnicity<span className="text-graphite"> ⓘ</span>
          </Tip>
          <div className="space-y-0.5">
            {race.map((r) => (
              <div key={r.label} className="flex items-center gap-2 text-[12px]">
                <span className="text-graphite w-16 shrink-0">{r.label}</span>
                <span className="flex-1 h-1.5 bg-hairline rounded-full overflow-hidden">
                  <span
                    className="block h-full bg-accent/70 rounded-full"
                    style={{ width: `${Math.round(r.share * 100)}%` }}
                  />
                </span>
                <span className="num text-ink w-8 text-right">{Math.round(r.share * 100)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
        </>
      )}
    </div>
  );
}

export default function DetailPanel() {
  const { metrics, weights, selectedZcta, metric } = useStore();
  const select = useStore((s) => s.select);
  const compareZctas = useStore((s) => s.compareZctas);
  const addCompare = useStore((s) => s.addCompare);
  const removeCompare = useStore((s) => s.removeCompare);
  const inCompare = selectedZcta != null && compareZctas.includes(selectedZcta);
  const m = selectedZcta ? metrics.get(selectedZcta) : undefined;
  const [rec, setRec] = useState<Record<string, unknown> | null>(null);
  const [recLoading, setRecLoading] = useState(false);

  // Desktop-only resizable width (drag the left edge). Persisted across selections.
  const [width, setWidth] = useState<number>(() => {
    const saved = Number(localStorage.getItem('ham_detail_width'));
    return saved >= 320 ? saved : 348;
  });
  const [isDesktop, setIsDesktop] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(min-width: 640px)').matches,
  );
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 640px)');
    const h = () => setIsDesktop(mq.matches);
    mq.addEventListener('change', h);
    return () => mq.removeEventListener('change', h);
  }, []);
  const startResize = (e: React.PointerEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = width;
    const maxW = Math.min(720, Math.round(window.innerWidth * 0.6));
    let last = startW;
    const onMove = (ev: PointerEvent) => {
      last = Math.max(320, Math.min(maxW, startW + (startX - ev.clientX))); // drag left = wider
      setWidth(last);
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      try { localStorage.setItem('ham_detail_width', String(last)); } catch { /* ignore */ }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Don't deselect the ZIP when Escape is closing the methodology modal stacked on top.
      if (e.key === 'Escape' && !useStore.getState().showMethodology) select(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [select]);

  // fetch the full record (raw measures) for the deepest drill-down level
  useEffect(() => {
    setRec(null);
    if (!selectedZcta) return;
    let live = true;
    setRecLoading(true);
    apiZcta(selectedZcta)
      .then((r) => {
        if (live) {
          setRec(r);
          setRecLoading(false);
        }
      })
      .catch(() => {
        if (live) {
          setRec(null);
          setRecLoading(false);
        }
      });
    return () => {
      live = false;
    };
  }, [selectedZcta]);

  const sortedScores = useMemo(() => buildScoreIndex(metrics.values(), weights), [metrics, weights]);
  // National rank index for the coincidence lens (the slim payload has no precomputed mult
  // percentile - it recomputes client-side, §RATIONALE). Only used when that lens is active.
  const sortedMult = useMemo(() => {
    const arr: number[] = [];
    for (const mm of metrics.values()) {
      const v = accessGapMult(mm, weights);
      if (v != null && !Number.isNaN(v)) arr.push(v);
    }
    return arr.sort((a, b) => a - b);
  }, [metrics, weights]);

  if (!m) return null;
  const score = accessGap(m, weights);
  const scorePercentile = percentileOf(sortedScores, score);

  return (
    <div className="relative w-full sm:w-auto" style={isDesktop ? { width } : undefined}>
      {isDesktop && (
        <div
          onPointerDown={startResize}
          onKeyDown={(e) => {
            if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
            e.preventDefault();
            const maxW = Math.min(720, Math.round(window.innerWidth * 0.6));
            setWidth((w) => {
              const next = Math.max(320, Math.min(maxW, w + (e.key === 'ArrowLeft' ? 24 : -24))); // left = wider
              try { localStorage.setItem('ham_detail_width', String(next)); } catch { /* ignore */ }
              return next;
            });
          }}
          tabIndex={0}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize panel (arrow keys)"
          title="Drag to resize"
          className="absolute left-0 inset-y-0 z-20 -ml-1.5 flex w-3 cursor-ew-resize items-center justify-center group focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        >
          <div className="h-10 w-1 rounded-full bg-hairline group-hover:bg-accent transition-colors" />
        </div>
      )}
      <div role="region" aria-label="ZIP detail" className="panel rounded-md w-full max-h-[64vh] sm:max-h-[calc(100vh-110px)] overflow-y-auto">
      <div className="px-4 pt-3 pb-2 border-b border-hairline sticky top-0 bg-surface z-10">
        <div className="flex justify-between items-start">
          <div className="min-w-0">
            <div
              className="font-serif text-[21px] text-ink leading-tight truncate"
              title={m.city ?? m.county_name ?? `ZIP ${m.zcta5}`}
            >
              {m.city ?? m.county_name ?? `ZIP ${m.zcta5}`}
            </div>
            <div className="text-[11px] text-graphite mt-0.5">
              <span className="num">ZIP {m.zcta5}</span>
              {m.city && m.county_name ? ` · ${m.county_name}` : ''}
              {m.state_name ? ` · ${m.state_name}` : m.state ? ` · ${m.state}` : ''}
            </div>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => (inCompare ? removeCompare(m.zcta5) : addCompare(m.zcta5))}
              aria-pressed={inCompare}
              className={`text-[11px] rounded border px-1.5 py-0.5 whitespace-nowrap ${
                inCompare
                  ? 'border-accent text-accent bg-accent/8'
                  : 'border-hairline text-graphite hover:border-accent hover:text-accent'
              }`}
              title="Compare this ZIP side-by-side with others"
            >
              {inCompare ? '✓ Comparing' : '＋ Compare'}
            </button>
            <button
              onClick={() => select(null)}
              aria-label="Close panel"
              className="grid place-items-center w-6 h-6 text-graphite hover:text-ink text-[16px] leading-none"
            >
              ✕
            </button>
          </div>
        </div>
      </div>

      <div className="px-4 py-3">
        {m.low_confidence && (
          <div className="mb-3 text-[12px] text-accent bg-accent/8 border border-accent/20 rounded px-2 py-1.5">
            Low-confidence area - small population ({fmtInt(m.population as number)}), wide margins.
          </div>
        )}
        {m.institutional && (
          <div className="mb-3 text-[12px] text-accent bg-accent/8 border border-accent/20 rounded px-2 py-1.5">
            Institutional ZIP - more registered providers than residents (a hospital campus, medical
            school, or VA complex). The supply reflects a workplace, not the local population, so raw
            per-capita figures are not meaningful and this area is held out of headline rankings.
          </div>
        )}
        {m.n_dims_scored != null && m.n_dims_scored < 3 && (
          <div className="mb-3 text-[12px] text-accent bg-accent/8 border border-accent/20 rounded px-2 py-1.5">
            Partial score - built from {m.n_dims_scored} of 3 dimensions (one had no usable data
            here), so it is a weaker estimate than a full 3-dimension score. Compare with care.
          </div>
        )}

        {(() => {
          if (score == null || scorePercentile == null) {
            return (
              <div className="text-[12px] text-graphite mt-1 leading-snug">
                Insufficient reliable data to score this area.
              </div>
            );
          }
          // The headline tracks the active map lens so the number + copy match what's coloured on
          // the map. (Bug fixed here: a within-state / coincidence / net-of-deprivation lens still
          // read "worse than X% of U.S. ZIPs ... nationally".) The comparison grid + drivers below
          // stay on the canonical national composite, so every framing remains visible.
          const worst = (p: number) => Math.max(1, Math.round(100 - p));
          const stateName = m.state_name ?? 'its state';
          let hPct: number | null = scorePercentile;
          let rankLabel = 'disadvantage rank';
          let sentence =
            `Higher = more access disadvantage (need + vulnerability + barriers combined). This ZIP is more disadvantaged than ${fmtScore(Math.min(99, scorePercentile))}% of U.S. ZIPs - among the most disadvantaged ${worst(scorePercentile)}% nationally. Use the range and peer ranks below before treating nearby ZIPs as meaningfully different.`;
          if (metric === WITHIN_STATE_METRIC && m.access_gap_pctile_within_state != null) {
            hPct = m.access_gap_pctile_within_state;
            rankLabel = 'within-state rank';
            sentence = `Higher = more access disadvantage. Within ${stateName}, this ZIP is more disadvantaged than ${fmtScore(Math.min(99, hPct))}% of ZIPs - among the most disadvantaged ${worst(hPct)}% in its state. (National rank is in the grid below.)`;
          } else if (metric === ACCESS_RESID_METRIC && m.care_access_resid_pctile != null) {
            hPct = m.care_access_resid_pctile;
            rankLabel = 'net-of-deprivation rank';
            sentence = `Barriers to care after health need + social vulnerability are removed. This ZIP's structural access is worse than ${fmtScore(Math.min(99, hPct))}% of U.S. ZIPs - i.e. barriers worse than its deprivation alone predicts.`;
          } else if (metric === COMPOSITE_MULT_METRIC) {
            const mp = percentileOf(sortedMult, accessGapMult(m, weights));
            if (mp != null) {
              hPct = mp;
              rankLabel = 'coincidence rank';
              sentence = `Where high need and high barriers coincide (geometric blend). This ZIP is worse than ${fmtScore(Math.min(99, hPct))}% of U.S. ZIPs on the coincidence lens - one-dimensional highs are down-weighted.`;
            }
          }
          const sev = hPct != null ? severity(hPct) : null;
          return (
            <>
              <div className="flex items-baseline gap-2 flex-wrap">
                <span
                  className="num text-[34px] font-semibold leading-none"
                  style={{ color: sev ? sev.color : undefined }}
                >
                  {fmtScore(hPct)}
                </span>
                <span className="text-[12px] text-graphite">/ 100 · {rankLabel}</span>
                {sev && (
                  <span
                    className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5"
                    style={{ color: sev.color, backgroundColor: `${sev.color}14` }}
                  >
                    <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: sev.color }} />
                    {sev.label}
                  </span>
                )}
              </div>
              <div className="text-[12px] text-graphite mt-1 leading-snug">{sentence}</div>
              <ComparisonFrame m={m} scorePercentile={scorePercentile} />
            </>
          );
        })()}

        {score != null && (
          <p className="font-serif text-[14px] text-ink leading-snug mt-2.5">
            {synthesize(m, weights)}
          </p>
        )}

        <DriversSection m={m} weights={weights} score={score} scorePercentile={scorePercentile} />

        <WhoLivesHere m={m} rec={rec} />

        {/* drill-down: dimensions -> sub-scores -> measures */}
        <div className="mt-3 pt-2.5 border-t border-hairline">
          <div className="text-[11px] uppercase tracking-wide text-graphite">
            Explore the layers <span className="text-graphite">(tap to drill in)</span>
          </div>
          {MODEL.map((dim) => (
            <Dimension key={dim.key} dim={dim} m={m} rec={rec} recLoading={recLoading} />
          ))}
        </div>

        {/* supply reality + context from the API record */}
        {rec && (
          <div className="mt-3 pt-2.5 border-t border-hairline text-[11px] text-graphite leading-snug">
            {typeof rec.primary_2sfca === 'number' && (
              <div>
                Spatial primary-care access (2SFCA):{' '}
                <span className="num text-ink">{(rec.primary_2sfca as number).toFixed(1)}/1k</span>
                {typeof rec.primary_people_per_provider === 'number'
                  ? ` · ≈1 per ${fmtInt(rec.primary_people_per_provider as number)} within 16 km`
                  : ''}
                {rec.primary_shortage === true ? (
                  <span className="text-accent font-medium">
                    {' '}
                    · below the HRSA 3,500:1 benchmark - likely a primary-care shortage (spatial access, not an HPSA designation)
                  </span>
                ) : (
                  ' · above the HRSA 3,500:1 benchmark'
                )}
              </div>
            )}
            {typeof rec.fqhc_sites_reachable === 'number' && (
              <div className="mt-1">
                Safety net:{' '}
                {(rec.fqhc_sites_reachable as number) > 0 ? (
                  <span>
                    <span className="num text-ink">{fmtInt(rec.fqhc_sites_reachable as number)}</span>{' '}
                    FQHC site{rec.fqhc_sites_reachable === 1 ? '' : 's'} within ~16 km
                    {typeof rec.nearest_fqhc_km === 'number'
                      ? `, nearest ${(rec.nearest_fqhc_km as number).toFixed(1)} km (straight-line)`
                      : ''}{' '}
                    (sliding-fee clinics serving the uninsured)
                  </span>
                ) : (
                  <span className="text-accent font-medium">
                    no FQHC within ~16 km - a safety-net desert
                  </span>
                )}
              </div>
            )}
            {typeof rec.medicaid_rate === 'number' && (
              <div className="mt-1 text-graphite">
                Medicaid share (shown above) is <i>acceptability</i> context - the population that
                can face provider Medicaid-acceptance barriers. It is not scored (as a barrier it
                tracks poverty, already counted).
              </div>
            )}
          </div>
        )}

        {/* OUTCOME (independent, not in the score) */}
        {m.life_expectancy != null && (
          <div className="mt-2 text-[11px] text-graphite">
            Outcome - life expectancy at birth:{' '}
            <span className="num text-ink font-medium">{m.life_expectancy} yrs</span>
            {m.life_expectancy_pctile != null
              ? ` (lower than ${fmtScore(Math.min(99, m.life_expectancy_pctile))}% of U.S. ZIPs)`
              : ''}
            <span className="text-graphite"> · CDC USALEEP, independent of the score</span>
          </div>
        )}

        <div className="mt-3 text-[11px] text-graphite leading-snug">
          Disease/behavior values are modeled CDC PLACES estimates (BRFSS), not counts. Provider
          access is a 2SFCA catchment metric over registered providers.
        </div>
      </div>
      </div>
    </div>
  );
}
