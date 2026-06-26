/// <reference lib="webworker" />
// Off-main-thread loader: fetches + JSON.parses the large payloads (~30 MB metrics + the
// low-zoom overview geojson) and computes polygon centroids, so the UI thread stays responsive
// (spinner keeps animating) during cold load. The heavy JSON.parse is the win moved off the
// main thread. Detailed geometry is NOT parsed here - it streams as vector tiles (zcta.pmtiles).

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

interface GeoFeature {
  type: 'Feature';
  properties: { zcta5: string };
  geometry: { type: string; coordinates: unknown } | null;
}

self.onmessage = async (e: MessageEvent<{ metricsUrl: string; geoUrl: string }>) => {
  try {
    const { metricsUrl, geoUrl } = e.data;
    const [mRes, gRes] = await Promise.all([fetch(metricsUrl), fetch(geoUrl)]);
    if (!mRes.ok) throw new Error(`metrics.json ${mRes.status}`);
    if (!gRes.ok) throw new Error(`zcta_overview.geojson ${gRes.status}`);
    const records = await mRes.json();
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
