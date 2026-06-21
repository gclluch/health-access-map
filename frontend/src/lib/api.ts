// Dynamic API (FastAPI). Proxied through Vite at /api. The app degrades
// gracefully if this is down -- the map + metrics.json are static (§13.3).
export interface ApiZcta {
  zcta5: string;
  [k: string]: unknown;
}

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json() as Promise<T>;
}

export const apiHealth = () =>
  getJson<{ status: string; zcta_count: number; states: string[] }>('/api/health');

// Full per-ZIP record (all ~55 raw measures) for the drill-down's deepest level.
export const apiZcta = (z: string) => getJson<Record<string, unknown>>(`/api/zcta/${z}`);

export const apiCompare = (zips: string[]) =>
  getJson<{ results: ApiZcta[] }>(`/api/compare?zips=${zips.join(',')}`);
