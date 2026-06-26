// Dynamic API (FastAPI). In dev, Vite proxies same-origin /api -> :8000. In prod the API
// may live on another origin, so the base is env-driven (VITE_API_BASE, e.g.
// "https://api.healthaccessmap.org"); empty default keeps same-origin /api. The app degrades
// gracefully if this is down -- the map + metrics.json are static (§13.3).
export interface ApiZcta {
  zcta5: string;
  [k: string]: unknown;
}

const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '');
const TIMEOUT_MS = 8000;

// One bounded fetch: abort after TIMEOUT_MS so a hung API never leaves the panel spinning forever.
async function fetchJsonOnce<T>(path: string): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const r = await fetch(`${API_BASE}${path}`, { signal: ctrl.signal });
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return (await r.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

// Retry once on transient failure (timeout / network / 5xx) before surfacing the error, so a
// single blip doesn't strand the drill-down. A 4xx (e.g. 404 unknown ZIP) is not retried.
async function getJson<T>(path: string): Promise<T> {
  try {
    return await fetchJsonOnce<T>(path);
  } catch (e) {
    const status = Number((e as Error).message?.match(/^(\d{3})/)?.[1]);
    if (status && status < 500) throw e; // client error -> won't change on retry
    return fetchJsonOnce<T>(path);
  }
}

export const apiHealth = () =>
  getJson<{ status: string; zcta_count: number; states: string[] }>('/api/health');

// Full per-ZIP record (all ~55 raw measures) for the drill-down's deepest level.
export const apiZcta = (z: string) => getJson<Record<string, unknown>>(`/api/zcta/${z}`);

export const apiCompare = (zips: string[]) =>
  getJson<{ results: ApiZcta[] }>(`/api/compare?zips=${encodeURIComponent(zips.join(','))}`);
