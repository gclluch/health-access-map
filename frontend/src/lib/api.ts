// Per-ZIP drill-down data. Production is static-only: the deepest detail comes from pre-built
// per-ZIP3 shards (/zcta/{zip3}.json, pipeline/build_shards.py) served as static files -- there is
// no live backend in the deployed app. (backend/ is a dev/test convenience, exercised by
// tests/test_backend.py; not on the prod path.) The map degrades gracefully if a shard is missing.
export interface ApiZcta {
  zcta5: string;
  [k: string]: unknown;
}

const TIMEOUT_MS = 8000;

// One bounded fetch: abort after TIMEOUT_MS so a hung request never leaves the panel spinning forever.
async function fetchJsonOnce<T>(path: string): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const r = await fetch(path, { signal: ctrl.signal });
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

// Full per-ZIP record (all raw measures + national percentiles) for the drill-down's deepest level
// and the Who-lives-here block, read from a pre-built per-ZIP3 shard at /zcta/{zip3}.json
// (pipeline/build_shards.py). One shard (~150 KB) is fetched per prefix and cached. A rejected shard
// is evicted so a transient failure can retry on the next click.
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
  const shard = await loadShard(z.slice(0, 3));
  const rec = shard[z];
  if (!rec) throw new Error(`404 /zcta/${z}`);
  return rec;
}

// Compare enrichment from the same shards as the drill-down (no separate endpoint). Best-effort per
// ZIP: a missing shard/record just drops that column, so one gap never fails the whole compare.
export async function apiCompare(zips: string[]): Promise<{ results: ApiZcta[] }> {
  const recs = await Promise.all(
    zips.map(async (z) => {
      try {
        const shard = await loadShard(z.slice(0, 3));
        const rec = shard[z];
        return rec ? ({ ...rec, zcta5: z } as ApiZcta) : null;
      } catch {
        return null;
      }
    }),
  );
  return { results: recs.filter((r): r is ApiZcta => r !== null) };
}
