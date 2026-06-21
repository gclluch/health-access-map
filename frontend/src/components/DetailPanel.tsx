import { useEffect, useMemo, useState } from 'react';
import { useStore } from '../store';
import { accessGap, dimensionContributions } from '../lib/scoring';
import { synthesize } from '../lib/synthesis';
import { MODEL, type DimSpec, type SlimMetric } from '../lib/types';
import { SUBSCORE_MEASURES, fmtMeasure } from '../lib/measures';
import { apiZcta } from '../lib/api';
import { fmtInt, fmtScore, ordinal } from '../lib/format';

// A percentile bar (0-100). Higher = worse (more gap), so more fill = worse.
function PctBar({ pct }: { pct: number | null | undefined }) {
  if (pct == null) return <div className="h-1.5 bg-hairline rounded-full" />;
  return (
    <div className="h-1.5 bg-hairline rounded-full overflow-hidden">
      <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
    </div>
  );
}

// Deepest level: individual measures for a sub-score, from the full API record.
function Measures({ subKey, rec }: { subKey: string; rec: Record<string, unknown> | null }) {
  const measures = SUBSCORE_MEASURES[subKey] ?? [];
  if (!rec) return <div className="px-3 py-1.5 text-[10px] text-graphite">Loading measures…</div>;
  return (
    <div className="px-3 py-1.5 bg-paper/60">
      {measures.map((mm) => (
        <div key={mm.col} className="flex justify-between text-[11px] py-0.5">
          <span className="text-graphite truncate pr-2">{mm.label}</span>
          <span className="num text-ink">{fmtMeasure(rec[mm.col], mm.unit)}</span>
        </div>
      ))}
    </div>
  );
}

function SubScoreRow({
  subKey,
  label,
  pct,
  rec,
}: {
  subKey: string;
  label: string;
  pct: number | null | undefined;
  rec: Record<string, unknown> | null;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-hairline/60">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-paper"
        aria-expanded={open}
      >
        <span className="text-graphite text-[9px] w-2">{open ? '▾' : '▸'}</span>
        <span className="flex-1 text-[12px] text-ink truncate">{label}</span>
        <span className="num text-[10px] text-graphite w-14 text-right">
          {pct == null ? 'no data' : `${ordinal(pct)} pct`}
        </span>
        <span className="w-16">
          <PctBar pct={pct} />
        </span>
      </button>
      {open && <Measures subKey={subKey} rec={rec} />}
    </div>
  );
}

function Dimension({
  dim,
  m,
  rec,
}: {
  dim: DimSpec;
  m: SlimMetric;
  rec: Record<string, unknown> | null;
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
        <span className="text-graphite text-[10px] w-2">{open ? '▾' : '▸'}</span>
        <span className="flex-1 text-[12.5px] font-medium text-ink">{dim.label}</span>
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
              pct={m[`${s.key}_pctile`] as number | null}
              rec={rec}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function DetailPanel() {
  const { metrics, weights, selectedZcta } = useStore();
  const select = useStore((s) => s.select);
  const m = selectedZcta ? metrics.get(selectedZcta) : undefined;
  const [rec, setRec] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') select(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [select]);

  // fetch the full record (raw measures) for the deepest drill-down level
  useEffect(() => {
    setRec(null);
    if (!selectedZcta) return;
    let live = true;
    apiZcta(selectedZcta)
      .then((r) => live && setRec(r))
      .catch(() => live && setRec(null));
    return () => {
      live = false;
    };
  }, [selectedZcta]);

  const sortedScores = useMemo(() => {
    const arr: number[] = [];
    for (const mm of metrics.values()) {
      const s = accessGap(mm, weights);
      if (s != null) arr.push(s);
    }
    return arr.sort((a, b) => a - b);
  }, [metrics, weights]);

  if (!m) return null;
  const score = accessGap(m, weights);
  const scorePercentile = (() => {
    if (score == null || !sortedScores.length) return null;
    let lo = 0;
    let hi = sortedScores.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (sortedScores[mid] < score) lo = mid + 1;
      else hi = mid;
    }
    return (lo / sortedScores.length) * 100;
  })();
  const contrib = dimensionContributions(m, weights);

  return (
    <div className="panel rounded-md w-full sm:w-[348px] max-h-[64vh] sm:max-h-[calc(100vh-110px)] overflow-y-auto">
      <div className="px-4 pt-3 pb-2 border-b border-hairline sticky top-0 bg-surface z-10">
        <div className="flex justify-between items-start">
          <div className="min-w-0">
            <div className="font-serif text-[19px] text-ink leading-tight truncate">
              {m.city ?? m.county_name ?? `ZIP ${m.zcta5}`}
            </div>
            <div className="text-[11px] text-graphite mt-0.5">
              <span className="num">ZIP {m.zcta5}</span>
              {m.city && m.county_name ? ` · ${m.county_name}` : ''}
              {m.state_name ? ` · ${m.state_name}` : m.state ? ` · ${m.state}` : ''}
            </div>
          </div>
          <button
            onClick={() => select(null)}
            aria-label="Close panel"
            className="text-graphite hover:text-ink text-[16px] leading-none px-1"
          >
            ✕
          </button>
        </div>
      </div>

      <div className="px-4 py-3">
        {m.low_confidence && (
          <div className="mb-3 text-[11px] text-accent bg-accent/8 border border-accent/20 rounded px-2 py-1.5">
            Low-confidence area - small population ({fmtInt(m.population as number)}), wide margins.
          </div>
        )}

        <div className="flex items-baseline gap-2">
          <span className="num text-[34px] font-semibold text-ink leading-none">{fmtScore(score)}</span>
          <span className="text-[11px] text-graphite">/ 100 access gap</span>
        </div>
        <div className="text-[11px] text-graphite mt-0.5">
          {score == null
            ? 'Insufficient reliable data to score this area.'
            : `Worse access than ${fmtScore(scorePercentile)}% of U.S. ZIPs (relative rank)`}
        </div>
        {score != null && scorePercentile != null && m.access_gap_rank_lo != null && (
          <div className="text-[11px] text-graphite mt-1 bg-paper/70 border border-hairline rounded px-2 py-1.5 leading-snug">
            <span className="text-ink font-medium">Tier {Math.ceil(scorePercentile / 10)} of 10</span>
            {' · reliable range '}
            <span className="num text-ink">
              {Math.round(m.access_gap_rank_lo as number)}-{Math.round(m.access_gap_rank_hi as number)}
            </span>
            {' pct under reasonable re-weightings. Two ZIPs whose ranges overlap are not reliably different.'}
          </div>
        )}

        {score != null && (
          <p className="font-serif text-[13.5px] text-ink leading-snug mt-2.5">
            {synthesize(m, weights)}
          </p>
        )}

        {/* dimension contributions: each = percentile × normalized weight; they
            sum to the score. Bars are out of 100 so the scale is unambiguous. */}
        {contrib &&
          (() => {
            const wsum =
              weights.health_need + weights.social_vulnerability + weights.care_access || 1;
            const rows = [
              ['Health need', 'health_need', m.health_need_pctile, weights.health_need, contrib.health_need],
              ['Social vulnerability', 'social_vulnerability', m.social_vulnerability_pctile, weights.social_vulnerability, contrib.social_vulnerability],
              ['Barriers to care', 'care_access', m.care_access_pctile, weights.care_access, contrib.care_access],
            ] as Array<[string, string, number | null, number, number]>;
            return (
              <div className="mt-3 pt-2.5 border-t border-hairline">
                <div className="text-[11px] uppercase tracking-wide text-graphite mb-1.5">
                  What drives the gap
                </div>
                {rows.map(([label, key, pct, w, c]) => (
                  <div key={key} className="mb-1.5">
                    <div className="flex items-baseline gap-2">
                      <span className="text-[11px] text-ink flex-1">{label}</span>
                      <span className="num text-[10px] text-graphite">
                        {ordinal(pct)} pct × {Math.round((w / wsum) * 100)}%
                      </span>
                      <span className="num text-[12px] text-ink font-medium w-7 text-right">
                        {c.toFixed(0)}
                      </span>
                    </div>
                    <div className="h-2 bg-hairline rounded-full overflow-hidden mt-0.5">
                      <span
                        className="block h-full bg-accent rounded-full"
                        style={{ width: `${Math.min(100, c)}%` }}
                      />
                    </div>
                  </div>
                ))}
                <div className="text-[10px] text-graphite mt-1 leading-snug">
                  Each = that dimension's national percentile × its weight (default{' '}
                  <span className="num">Need 35 · Vuln 30 · Access 35</span>); bars are out of 100
                  and the three sum to the score (<span className="num">{fmtScore(score)}</span>).
                  The weights are a value judgment - need and access sit slightly above
                  vulnerability, kept near-equal - and you can re-tune them under "Customize the
                  score."
                </div>
              </div>
            );
          })()}

        {/* drill-down: dimensions -> sub-scores -> measures */}
        <div className="mt-3 pt-2.5 border-t border-hairline">
          <div className="text-[11px] uppercase tracking-wide text-graphite">
            Explore the layers <span className="text-graphite/70">(tap to drill in)</span>
          </div>
          {MODEL.map((dim) => (
            <Dimension key={dim.key} dim={dim} m={m} rec={rec} />
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
                  ? ` · ≈1 per ${fmtInt(rec.primary_people_per_provider as number)} reachable`
                  : ''}
                {rec.primary_shortage === true ? (
                  <span className="text-accent font-medium">
                    {' '}
                    · below HRSA 3,500:1 - a real provider shortage
                  </span>
                ) : (
                  ' · above HRSA 3,500:1 shortage threshold'
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
                      ? `, nearest ${(rec.nearest_fqhc_km as number).toFixed(1)} km`
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
            <div className="mt-1">
              Population <span className="num text-ink">{fmtInt(m.population as number)}</span>
              {typeof rec.median_age === 'number'
                ? ` · median age ${Math.round(rec.median_age as number)}`
                : ''}
              {typeof rec.pct_minority === 'number'
                ? ` · ${Math.round((rec.pct_minority as number) * 100)}% minority`
                : ''}
            </div>
          </div>
        )}

        {/* OUTCOME (independent, not in the score) */}
        {m.life_expectancy != null && (
          <div className="mt-2 text-[11px] text-graphite">
            Outcome - life expectancy at birth:{' '}
            <span className="num text-ink font-medium">{m.life_expectancy} yrs</span>
            {m.life_expectancy_pctile != null
              ? ` (lower than ${fmtScore(m.life_expectancy_pctile)}% of U.S. ZIPs)`
              : ''}
            <span className="text-graphite/80"> · CDC USALEEP, independent of the score</span>
          </div>
        )}

        <div className="mt-3 text-[10px] text-graphite leading-snug">
          Disease/behavior values are modeled CDC PLACES estimates (BRFSS), not counts. Provider
          access is a 2SFCA catchment metric over registered providers. Every score is a relative
          national rank; higher = worse.
        </div>
      </div>
    </div>
  );
}
