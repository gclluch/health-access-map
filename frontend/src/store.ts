import { create } from 'zustand';
import { loadData, type FeatureCollection } from './lib/data';
import { track } from './lib/observability';
import { parseWeightParam } from './lib/scoring';
import {
  ALL_METRICS,
  COMPOSITE_METRIC,
  WITHIN_STATE_METRIC,
  DEFAULT_WEIGHTS,
  LAZY_METRICS,
  SUBSCORE_LAZY_COLS,
  parseAnchors,
  PRESETS,
  type AnchorPreset,
  type BuildMeta,
  type SlimMetric,
  type SubscoreCorrelations,
  type Weights,
} from './lib/types';

type Status = 'loading' | 'ready' | 'error';

export interface FlyTarget {
  longitude: number;
  latitude: number;
  zoom: number;
  nonce: number;
}

interface AppState {
  status: Status;
  error: string | null;
  metrics: Map<string, SlimMetric>;
  // Sub-score lens columns (subscores.json) load lazily on first sub-score metric select (T8).
  subscoresStatus: 'idle' | 'loading' | 'ready' | 'error';
  overview: FeatureCollection | null; // low-zoom geometry; detail streams from pmtiles
  centroids: Map<string, [number, number]>;
  bounds: [[number, number], [number, number]] | null;
  stateBounds: Map<string, [[number, number], [number, number]]>;
  availableStates: string[];

  metric: string;
  weights: Weights;
  anchors: AnchorPreset[];
  meta: BuildMeta | null;
  // Display-only poverty-rank trend (pipeline/build_trends.py); never part of the score.
  trends: { prior: number; curr: number; deltas: Map<string, number> } | null;
  subscoreCorrelations: SubscoreCorrelations;
  selectedZcta: string | null;
  hoveredZcta: string | null;
  compareZctas: string[];
  stateFilter: string | null;
  rankOrder: 'desc' | 'asc';
  flyTarget: FlyTarget | null;
  fitTarget: { bounds: [[number, number], [number, number]]; nonce: number } | null;
  locating: boolean;
  toast: string | null;

  showWeights: boolean;
  showMethodology: boolean;

  load: () => Promise<void>;
  ensureSubscoreColumns: () => Promise<void>;
  setMetric: (m: string) => void;
  setWeights: (w: Partial<Weights>) => void;
  resetWeights: () => void;
  applyPreset: (name: string) => void;
  select: (z: string | null, opts?: { fly?: boolean }) => void;
  hover: (z: string | null) => void;
  addCompare: (z: string) => void;
  removeCompare: (z: string) => void;
  clearCompare: () => void;
  jumpToState: (s: string | null) => void;
  setRankOrder: (o: 'desc' | 'asc') => void;
  toggleWeights: () => void;
  toggleMethodology: (v?: boolean) => void;
  flyTo: (z: string) => void;
  locateMe: () => void;
  setToast: (m: string | null) => void;
}

function readUrl(): Partial<Pick<AppState, 'metric' | 'weights' | 'selectedZcta'>> {
  const p = new URLSearchParams(location.search);
  const out: Partial<Pick<AppState, 'metric' | 'weights' | 'selectedZcta'>> = {};
  const m = p.get('metric');
  if (m && ALL_METRICS.includes(m)) out.metric = m;
  const z = p.get('zip');
  if (z && /^\d{5}$/.test(z)) out.selectedZcta = z;
  const weights = parseWeightParam(p.get('w'));
  if (weights) out.weights = weights;
  return out;
}

let loadStarted = false;
let subscorePromise: Promise<void> | null = null; // cache the one-time subscores.json fetch+merge
let urlTimer: ReturnType<typeof setTimeout> | undefined;
function syncUrl(s: AppState) {
  clearTimeout(urlTimer);
  urlTimer = setTimeout(() => {
    const p = new URLSearchParams();
    p.set('metric', s.metric);
    p.set('w', `${s.weights.health_need},${s.weights.social_vulnerability},${s.weights.care_access}`);
    if (s.selectedZcta) p.set('zip', s.selectedZcta);
    history.replaceState(null, '', `?${p.toString()}`);
  }, 300);
}

export const useStore = create<AppState>((set, get) => ({
  status: 'loading',
  error: null,
  metrics: new Map(),
  subscoresStatus: 'idle',
  overview: null,
  centroids: new Map(),
  bounds: null,
  stateBounds: new Map(),
  availableStates: [],

  metric: COMPOSITE_METRIC,
  weights: { ...DEFAULT_WEIGHTS },
  anchors: [],
  meta: null,
  trends: null,
  subscoreCorrelations: {},
  selectedZcta: null,
  hoveredZcta: null,
  compareZctas: [],
  stateFilter: null,
  rankOrder: 'desc',
  flyTarget: null,
  fitTarget: null,
  locating: false,
  toast: null,
  showWeights: false,
  showMethodology: false,

  load: async () => {
    if (loadStarted) return; // guard React StrictMode double-invoke
    loadStarted = true;
    try {
      const data = await loadData();
      // multi-anchor outcome validation (pipeline/validate.py), if present
      fetch('/weights.json')
        .then((r) => (r.ok ? r.json() : null))
        .then((w) => {
          if (w?.anchors)
            set({ anchors: parseAnchors(w), subscoreCorrelations: w.subscore_correlations ?? {} });
        })
        .catch(() => {});
      // build metadata for the "data as of" freshness badge (optional)
      fetch('/meta.json')
        .then((r) => (r.ok ? r.json() : null))
        .then((mt) => {
          if (mt?.generated) set({ meta: mt });
        })
        .catch(() => {});
      // poverty-rank trend (pipeline/build_trends.py), if present - display-only
      fetch('/trends.json')
        .then((r) => (r.ok ? r.json() : null))
        .then((t) => {
          if (t?.deltas) {
            set({ trends: { prior: t.prior, curr: t.curr,
              deltas: new Map(Object.entries(t.deltas) as [string, number][]) } });
          }
        })
        .catch(() => {});
      // Fit to the continental US by default: AK/HI/PR centroids otherwise stretch
      // the initial view off-center. Fall back to full extent if nothing is in the
      // CONUS box (e.g. a dev-state run of HI/AK).
      const inConus = (lon: number, lat: number) =>
        lon >= -125 && lon <= -66 && lat >= 24 && lat <= 50;
      let minLon = 180;
      let minLat = 90;
      let maxLon = -180;
      let maxLat = -90;
      let conusCount = 0;
      for (const [lon, lat] of data.centroids.values()) {
        if (!inConus(lon, lat)) continue;
        conusCount += 1;
        minLon = Math.min(minLon, lon);
        minLat = Math.min(minLat, lat);
        maxLon = Math.max(maxLon, lon);
        maxLat = Math.max(maxLat, lat);
      }
      if (conusCount === 0) {
        for (const [lon, lat] of data.centroids.values()) {
          minLon = Math.min(minLon, lon);
          minLat = Math.min(minLat, lat);
          maxLon = Math.max(maxLon, lon);
          maxLat = Math.max(maxLat, lat);
        }
      }
      // per-state bounds for the quick-jump, from each ZIP's centroid + state.
      const sb = new Map<string, [[number, number], [number, number]]>();
      for (const [z, m] of data.metrics) {
        const c = data.centroids.get(z);
        if (!c || !m.state) continue;
        const b = sb.get(m.state);
        if (!b) sb.set(m.state, [[c[0], c[1]], [c[0], c[1]]]);
        else {
          b[0][0] = Math.min(b[0][0], c[0]);
          b[0][1] = Math.min(b[0][1], c[1]);
          b[1][0] = Math.max(b[1][0], c[0]);
          b[1][1] = Math.max(b[1][1], c[1]);
        }
      }
      const url = readUrl();
      set({
        status: 'ready',
        metrics: data.metrics,
        overview: data.overview,
        centroids: data.centroids,
        bounds: [
          [minLon, minLat],
          [maxLon, maxLat],
        ],
        stateBounds: sb,
        availableStates: [...sb.keys()].sort(),
        ...url,
      });
      if (url.selectedZcta) get().flyTo(url.selectedZcta);
      // Deep-link straight to a sub-score lens (?metric=insurance_pctile): load its columns now.
      if (LAZY_METRICS.has(get().metric)) get().ensureSubscoreColumns().catch(() => {});
      syncUrl(get());
    } catch (e) {
      set({ status: 'error', error: e instanceof Error ? e.message : String(e) });
    }
  },

  // Fetch subscores.json once and merge its columns onto the already-loaded SlimMetric records, so
  // the sub-score map lenses colour. Cached: repeat calls (or a second lens) reuse the one promise.
  ensureSubscoreColumns: () => {
    if (subscorePromise) return subscorePromise;
    set({ subscoresStatus: 'loading' });
    subscorePromise = fetch('/subscores.json')
      .then((r) => {
        if (!r.ok) throw new Error(`subscores.json ${r.status}`);
        return r.json();
      })
      .then((s: { zcta5: string[] } & Record<string, Array<number | null>>) => {
        const metrics = get().metrics;
        for (let i = 0; i < s.zcta5.length; i++) {
          const rec = metrics.get(s.zcta5[i]);
          if (!rec) continue;
          for (const col of SUBSCORE_LAZY_COLS) rec[col] = s[col][i];
        }
        // New Map reference so map/rankings subscribers re-render and read the merged columns.
        set({ metrics: new Map(metrics), subscoresStatus: 'ready' });
      })
      .catch((e) => {
        subscorePromise = null; // allow a retry on the next lens select
        set({ subscoresStatus: 'error' });
        throw e;
      });
    return subscorePromise;
  },

  setMetric: (m) => {
    set({ metric: m });
    if (LAZY_METRICS.has(m)) get().ensureSubscoreColumns().catch(() => {});
    track('metric_changed', { metric: m });
    syncUrl(get());
  },
  setWeights: (w) => {
    set({ weights: { ...get().weights, ...w } });
    syncUrl(get());
  },
  resetWeights: () => {
    set({ weights: { ...DEFAULT_WEIGHTS } });
    syncUrl(get());
  },
  applyPreset: (name) => {
    const p = PRESETS[name];
    if (p) {
      set({ weights: { ...p } });
      syncUrl(get());
    }
  },
  select: (z, opts) => {
    set({ selectedZcta: z });
    if (z) track('zcta_selected', { zcta: z });
    if (z && opts?.fly) get().flyTo(z);
    syncUrl(get());
  },
  hover: (z) => set({ hoveredZcta: z }),
  addCompare: (z) =>
    set((s) => (s.compareZctas.includes(z) || s.compareZctas.length >= 5
      ? s
      : { compareZctas: [...s.compareZctas, z] })),
  removeCompare: (z) => set((s) => ({ compareZctas: s.compareZctas.filter((x) => x !== z) })),
  clearCompare: () => set({ compareZctas: [] }),
  setRankOrder: (o) => set({ rankOrder: o }),
  jumpToState: (s) => {
    set({ stateFilter: s });
    // The within-state lens is only meaningful inside a chosen state; clearing the state filter
    // would leave it selected but no longer offered, so snap back to the national composite.
    if (!s && get().metric === WITHIN_STATE_METRIC) set({ metric: COMPOSITE_METRIC });
    const b = s ? get().stateBounds.get(s) : get().bounds;
    if (b) set({ fitTarget: { bounds: b, nonce: Date.now() } });
  },
  toggleWeights: () => set({ showWeights: !get().showWeights }),
  toggleMethodology: (v) => set({ showMethodology: v ?? !get().showMethodology }),
  flyTo: (z) => {
    const c = get().centroids.get(z);
    if (c) {
      set({
        flyTarget: { longitude: c[0], latitude: c[1], zoom: 9, nonce: Date.now() },
      });
    }
  },
  locateMe: () => {
    if (!navigator.geolocation) {
      set({ toast: 'Location is not available in this browser.' });
      return;
    }
    set({ locating: true });
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { longitude, latitude } = pos.coords;
        // nearest ZCTA centroid (linear scan over ~33k points is fine for a click)
        let best: string | null = null;
        let bestD = Infinity;
        for (const [z, [lon, lat]] of get().centroids) {
          const d = (lon - longitude) ** 2 + (lat - latitude) ** 2;
          if (d < bestD) {
            bestD = d;
            best = z;
          }
        }
        set({ locating: false });
        if (best) get().select(best, { fly: true });
        else set({ toast: 'No ZIP area found near your location.' });
      },
      () => set({ locating: false, toast: "Couldn't get your location - showing the national view." }),
      { timeout: 8000 },
    );
  },
  setToast: (m) => set({ toast: m }),
}));
