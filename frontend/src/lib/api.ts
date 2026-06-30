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

// Full per-ZIP record (all raw measures + national percentiles) for the drill-down's deepest
// level and the Who-lives-here block. Two sources, transparent to callers:
//  - If VITE_API_BASE is set, a real FastAPI backend is hosted -> hit /api/zcta/{z}.
//  - Otherwise (the static Netlify deploy) read a pre-built per-ZIP3 shard from /zcta/{zip3}.json
//    (pipeline/build_shards.py). One shard (~150 KB) is fetched per prefix and cached, so the
//    static site mirrors the backend with no server. A rejected shard is evicted so a transient
//    failure can retry on the next click.
const shardCache = new Map<string, Promise<Record<string, Record<string, unknown>>>>();

function loadShard(zip3: string): Promise<Record<string, Record<string, unknown>>> {
  let p = shardCache.get(zip3);
  if (!p) {
    p = getJson<Record<string, Record<string, unknown>>>(`/zcta/${zip3}.json`).catch((e) => {
      shardCache.delete(zip3);
      throw e;
    });
    shardCache.set(zip3, p);
  }
  return p;
}

export async function apiZcta(z: string): Promise<Record<string, unknown>> {
  if (API_BASE) return getJson<Record<string, unknown>>(`/api/zcta/${z}`);
  const shard = await loadShard(z.slice(0, 3));
  const rec = shard[z];
  if (!rec) throw new Error(`404 /zcta/${z}`);
  return rec;
}

export const apiCompare = (zips: string[]) =>
  getJson<{ results: ApiZcta[] }>(`/api/compare?zips=${encodeURIComponent(zips.join(','))}`);
