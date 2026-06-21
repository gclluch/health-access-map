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

export async function loadData(): Promise<LoadedData> {
  const [mRes, gRes] = await Promise.all([
    fetch('/metrics.json'),
    fetch('/zcta.geojson'),
  ]);
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
