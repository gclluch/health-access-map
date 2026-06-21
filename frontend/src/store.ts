import { create } from 'zustand';
import { loadData, type FeatureCollection } from './lib/data';
import {
  COMPOSITE_METRIC,
  DEFAULT_WEIGHTS,
  PRESETS,
  type SlimMetric,
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
  geojson: FeatureCollection | null;
  centroids: Map<string, [number, number]>;
  bounds: [[number, number], [number, number]] | null;
  stateBounds: Map<string, [[number, number], [number, number]]>;
  availableStates: string[];

  metric: string;
  weights: Weights;
  selectedZcta: string | null;
  hoveredZcta: string | null;
  stateFilter: string | null;
  rankOrder: 'desc' | 'asc';
  flyTarget: FlyTarget | null;
  fitTarget: { bounds: [[number, number], [number, number]]; nonce: number } | null;
  locating: boolean;
  toast: string | null;

  showWeights: boolean;
  showMethodology: boolean;

  load: () => Promise<void>;
  setMetric: (m: string) => void;
  setWeights: (w: Partial<Weights>) => void;
  resetWeights: () => void;
  applyPreset: (name: string) => void;
  select: (z: string | null, opts?: { fly?: boolean }) => void;
  hover: (z: string | null) => void;
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
  if (m) out.metric = m;
  const z = p.get('zip');
  if (z && /^\d{5}$/.test(z)) out.selectedZcta = z;
  const w = p.get('w');
  if (w) {
    const [h, s, c] = w.split(',').map(Number);
    if ([h, s, c].every((n) => !Number.isNaN(n)))
      out.weights = { health_need: h, social_vulnerability: s, care_access: c };
  }
  return out;
}

let loadStarted = false;
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
  geojson: null,
  centroids: new Map(),
  bounds: null,
  stateBounds: new Map(),
  availableStates: [],

  metric: COMPOSITE_METRIC,
  weights: { ...DEFAULT_WEIGHTS },
  selectedZcta: null,
  hoveredZcta: null,
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
        geojson: data.geojson,
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
      syncUrl(get());
    } catch (e) {
      set({ status: 'error', error: e instanceof Error ? e.message : String(e) });
    }
  },

  setMetric: (m) => {
    set({ metric: m });
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
    if (z && opts?.fly) get().flyTo(z);
    syncUrl(get());
  },
  hover: (z) => set({ hoveredZcta: z }),
  setRankOrder: (o) => set({ rankOrder: o }),
  jumpToState: (s) => {
    set({ stateFilter: s });
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
