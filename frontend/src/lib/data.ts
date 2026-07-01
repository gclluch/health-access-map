import type { SlimMetric } from './types';
import { centroid } from './geo';

export interface FeatureCollection {
  type: 'FeatureCollection';
  features: Array<{
    type: 'Feature';
    properties: { zcta5: string };
    geometry: { type: string; coordinates: unknown };
  }>;
}

export interface LoadedData {
  metrics: Map<string, SlimMetric>;
  // The low-zoom overview geometry (every ZCTA, heavily simplified). Detailed geometry for
  // z>=6 streams from zcta.pmtiles in the map; this drives the dense national choropleth.
  overview: FeatureCollection;
  centroids: Map<string, [number, number]>;
}

const METRICS_URL = '/map_frame.json';
const GEO_URL = '/zcta_overview.geojson';

// Columnar (struct-of-arrays) first-paint payload emitted by pipeline join_and_score._write_map_frame:
// { n, zcta5: [...], health_need_pctile: [...], scoreable: [0,1,...], ... }. Reconstructs into the
// SlimMetric[] the store already expects, so no consumer downstream changes.
export interface ColumnFrame {
  n: number;
  [col: string]: number | Array<string | number | null>;
}

// Frame columns serialized as 0/1 ints -> restore to booleans on the SlimMetric.
const FRAME_BOOL_COLS = new Set(['low_confidence', 'institutional', 'scoreable']);

export function framesToRecords(frame: ColumnFrame): SlimMetric[] {
  const n = frame.n;
  const cols = Object.keys(frame).filter((k) => k !== 'n');
  const records: SlimMetric[] = new Array(n);
  for (let i = 0; i < n; i++) {
    const rec: Record<string, string | number | boolean | null> = {};
    for (const c of cols) {
      const v = (frame[c] as Array<string | number | null>)[i];
      rec[c] = FRAME_BOOL_COLS.has(c) ? Boolean(v) : v;
    }
    records[i] = rec as unknown as SlimMetric;
  }
  return records;
}

// Try the Web Worker (off-main-thread parse); fall back to main-thread parse if Workers are
// unavailable or the worker errors. Keeps the cold-load JSON.parse off the UI thread when possible.
export async function loadData(): Promise<LoadedData> {
  try {
    if (typeof Worker !== 'undefined') return await loadViaWorker();
  } catch {
    /* fall through to main-thread parse */
  }
  return loadOnMainThread();
}

function loadViaWorker(): Promise<LoadedData> {
  return new Promise<LoadedData>((resolve, reject) => {
    const worker = new Worker(new URL('./dataWorker.ts', import.meta.url), { type: 'module' });
    worker.onmessage = (e: MessageEvent) => {
      const d = e.data;
      worker.terminate();
      if (!d?.ok) return reject(new Error(d?.error ?? 'data worker failed'));
      const metrics = new Map<string, SlimMetric>();
      for (const r of d.records as SlimMetric[]) metrics.set(r.zcta5, r);
      const centroids = new Map<string, [number, number]>();
      for (const [z, lon, lat] of d.centroids as Array<[string, number, number]>) {
        centroids.set(z, [lon, lat]);
      }
      resolve({ metrics, overview: d.geojson as FeatureCollection, centroids });
    };
    worker.onerror = (err) => {
      worker.terminate();
      reject(err.error ?? new Error('data worker error'));
    };
    worker.postMessage({ metricsUrl: METRICS_URL, geoUrl: GEO_URL });
  });
}

async function loadOnMainThread(): Promise<LoadedData> {
  const [mRes, gRes] = await Promise.all([fetch(METRICS_URL), fetch(GEO_URL)]);
  if (!mRes.ok) throw new Error(`map_frame.json ${mRes.status}`);
  if (!gRes.ok) throw new Error(`zcta_overview.geojson ${gRes.status}`);
  const records = framesToRecords((await mRes.json()) as ColumnFrame);
  const overview = (await gRes.json()) as FeatureCollection;

  // Some national ZCTAs ship with null geometry; they can't be drawn -> drop them.
  overview.features = overview.features.filter((f) => f.geometry && f.geometry.coordinates);

  const metrics = new Map<string, SlimMetric>();
  for (const r of records) metrics.set(r.zcta5, r);

  const centroids = new Map<string, [number, number]>();
  for (const f of overview.features) {
    centroids.set(f.properties.zcta5, centroid(f.geometry.coordinates));
  }
  return { metrics, overview, centroids };
}
