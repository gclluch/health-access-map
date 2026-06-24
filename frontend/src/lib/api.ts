// Dynamic API (FastAPI). In dev, Vite proxies same-origin /api -> :8000. In prod the API
// may live on another origin, so the base is env-driven (VITE_API_BASE, e.g.
// "https://api.healthaccessmap.org"); empty default keeps same-origin /api. The app degrades
// gracefully if this is down -- the map + metrics.json are static (§13.3).
export interface ApiZcta {
  zcta5: string;
  [k: string]: unknown;
}

const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '');

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json() as Promise<T>;
}

export const apiHealth = () =>
  getJson<{ status: string; zcta_count: number; states: string[] }>('/api/health');

// Full per-ZIP record (all ~55 raw measures) for the drill-down's deepest level.
export const apiZcta = (z: string) => getJson<Record<string, unknown>>(`/api/zcta/${z}`);

export const apiCompare = (zips: string[]) =>
  getJson<{ results: ApiZcta[] }>(`/api/compare?zips=${encodeURIComponent(zips.join(','))}`);
