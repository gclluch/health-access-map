/// <reference lib="webworker" />
// Off-main-thread loader: fetches + JSON.parses the payloads (the columnar first-paint map_frame +
// the low-zoom overview geojson), reconstructs the SlimMetric records, and computes polygon
// centroids, so the UI thread stays responsive (spinner keeps animating) during cold load. The heavy
// JSON.parse is the win moved off the main thread. Detailed geometry is NOT parsed here - it streams
// as vector tiles (zcta.pmtiles); sub-score lenses load lazily via subscores.json (see store.ts).

import { centroid } from './geo';
import { framesToRecords, type ColumnFrame } from './data';

interface GeoFeature {
  type: 'Feature';
  properties: { zcta5: string };
  geometry: { type: string; coordinates: unknown } | null;
}

self.onmessage = async (e: MessageEvent<{ metricsUrl: string; geoUrl: string }>) => {
  try {
    const { metricsUrl, geoUrl } = e.data;
    const [mRes, gRes] = await Promise.all([fetch(metricsUrl), fetch(geoUrl)]);
    if (!mRes.ok) throw new Error(`map_frame.json ${mRes.status}`);
    if (!gRes.ok) throw new Error(`zcta_overview.geojson ${gRes.status}`);
    const records = framesToRecords((await mRes.json()) as ColumnFrame);
    const geojson = (await gRes.json()) as { type: string; features: GeoFeature[] };
    geojson.features = geojson.features.filter((f) => f.geometry && f.geometry.coordinates);
    const centroids: Array<[string, number, number]> = [];
    for (const f of geojson.features) {
      const [lon, lat] = centroid(f.geometry!.coordinates);
      centroids.push([f.properties.zcta5, lon, lat]);
    }
    (self as DedicatedWorkerGlobalScope).postMessage({ ok: true, records, geojson, centroids });
  } catch (err) {
    (self as DedicatedWorkerGlobalScope).postMessage({
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    });
  }
};
