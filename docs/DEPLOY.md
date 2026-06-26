# Deploy

The app is two deployables: a **static SPA** (the map + the precomputed `metrics.json` /
`zcta.geojson`) and a small **FastAPI** service (per-ZIP drill-down, rankings, compare). The map
works from the static files alone; the API powers the detail-panel deep drill-down.

## Prerequisites

Both images bake in build outputs that are gitignored and reproducible:

```bash
make data        # -> data/processed/metrics.parquet
                 #    frontend/public/{metrics.json,zcta.geojson}
```

CI does not have these (the data stages need API keys + large downloads), which is why the
data-dependent pytest cases `skip` rather than fail when `metrics.parquet` is absent.

Before cutting a deploy from a real local/national build, run:

```bash
make prod-check
```

That target runs the backend/pipeline tests, frontend typecheck/unit/build, rank-band verification,
diagnostics, and `docker compose config`. Treat a skipped `pipeline.verify_bands` calibration gate
as not production-ready for rank-band claims; rebuild the debug artifacts and rerun before shipping.

## One-box (docker compose)

```bash
make data
docker compose up --build
open http://localhost:8080      # SPA; nginx proxies same-origin /api -> api:8000
```

`ALLOWED_ORIGINS` defaults to `http://localhost:8080` (the web origin the browser sends on the
CORS preflight). Set it to your real origin in production.

## Split deploy (static host + API host)

- **SPA** -> any static/CDN host. Build with the API origin baked in:
  ```bash
  cd frontend && VITE_API_BASE=https://api.example.org npm run build
  # upload dist/; set Cache-Control: assets/* immutable, *.json must-revalidate (see nginx.conf)
  ```
- **API** -> the backend image. Set CORS to the SPA origin:
  ```bash
  docker build -f backend/Dockerfile -t ham-api .
  docker run -e ALLOWED_ORIGINS=https://www.example.org -p 8000:8000 ham-api
  # preview deploys: ALLOWED_ORIGIN_REGEX='https://.*\.vercel\.app'
  ```

## Environment variables

| Var | Side | Default | Purpose |
|---|---|---|---|
| `ALLOWED_ORIGINS` | API | `http://localhost:8080` | comma-separated CORS allowlist |
| `ALLOWED_ORIGIN_REGEX` | API | (unset) | regex allowlist for preview deploys |
| `VITE_API_BASE` | SPA build | `""` (same-origin `/api`) | API origin for split deploys |
| `VITE_SENTRY_DSN` | SPA build | (unset) | enables client error reporting |
| `VITE_ANALYTICS_URL` | SPA build | (unset) | enables privacy-light usage beacons |

## Payload weight (know before you ship)

`metrics.json` (~28 MB raw / ~3.7 MB gzip) + `zcta.geojson` (~16.7 MB / ~4.5 MB gzip) are the
cold-load cost. Mitigations already in place: `gzip_static` pre-compressed files, immutable
hashed assets, a Web Worker that parses the payloads off the main thread, and split vendor
chunks. Not yet done (documented in README "Roadmap"): vector tiles / PMTiles for the geometry,
which is the real fix for the geojson weight.
