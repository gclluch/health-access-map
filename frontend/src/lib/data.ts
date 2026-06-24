import type { SlimMetric } from './types';

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
  geojson: FeatureCollection;
  centroids: Map<string, [number, number]>;
}

function centroid(coords: unknown): [number, number] {
  let sx = 0;
  let sy = 0;
  let n = 0;
  const walk = (c: unknown) => {
    if (Array.isArray(c) && typeof c[0] === 'number' && typeof c[1] === 'number') {
      sx += c[0] as number;
      sy += c[1] as number;
      n += 1;
    } else if (Array.isArray(c)) {
      c.forEach(walk);
    }
  };
  walk(coords);
  return n ? [sx / n, sy / n] : [-119, 37];
}

const METRICS_URL = '/metrics.json';
const GEO_URL = '/zcta.geojson';

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
      resolve({ metrics, geojson: d.geojson as FeatureCollection, centroids });
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
  if (!mRes.ok) throw new Error(`metrics.json ${mRes.status}`);
  if (!gRes.ok) throw new Error(`zcta.geojson ${gRes.status}`);
  const records = (await mRes.json()) as SlimMetric[];
  const geojson = (await gRes.json()) as FeatureCollection;

  // Some national ZCTAs ship with null geometry; they can't be drawn -> drop them.
  geojson.features = geojson.features.filter((f) => f.geometry && f.geometry.coordinates);

  const metrics = new Map<string, SlimMetric>();
  for (const r of records) metrics.set(r.zcta5, r);

  const centroids = new Map<string, [number, number]>();
  for (const f of geojson.features) {
    centroids.set(f.properties.zcta5, centroid(f.geometry.coordinates));
  }
  return { metrics, geojson, centroids };
}
