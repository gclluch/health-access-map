# Deploy

The app is two deployables: a **static SPA** (the map + the precomputed `map_frame.json` +
`subscores.json`, `zcta_overview.geojson`, and range-requested `zcta.pmtiles`) and a small **FastAPI** service
(per-ZIP drill-down, rankings, compare). The map
works from the static files alone; the API powers the detail-panel deep drill-down.

## Prerequisites

Both images bake in build outputs that are gitignored and reproducible:

```bash
make data        # -> data/processed/metrics.parquet
                 #    frontend/public/{map_frame.json,subscores.json,zcta_overview.geojson,zcta.pmtiles}
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

## Single-VPS production

The repo ships a Caddy overlay for the cheapest reliable production beta: nginx serves the SPA,
FastAPI stays internal, and Caddy terminates TLS.

```bash
make data
make prod-check
cp .env.prod.example .env
# edit DOMAIN and ALLOWED_ORIGINS
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

DNS for `DOMAIN` must point at the VPS, and only ports **80/443** need to be open publicly. The
base `api` and `web` ports bind to `127.0.0.1` for local debugging; external traffic should enter
through Caddy only.

Minimum practical VPS: **1 vCPU / 1 GB RAM / 10 GB disk**. Runtime data is small
(`metrics.parquet` is ~20 MB and expands to ~60 MB in pandas), but the full data pipeline should be
run on a machine with **25+ GB free disk** because NPPES is large.

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

`map_frame.json` (first-paint frame, ~2.6 MB raw / ~0.7 MB gzip), `zcta_overview.geojson` (~7 MB
raw / ~1.3 MB gzip), and `zcta.pmtiles` (~15 MB, range-requested) are the cold-load cost; the 14
sub-score lenses (`subscores.json`, ~1.7 MB raw / ~0.6 MB gzip) load lazily on first sub-score
select, off the cold path. Mitigations already in place: `gzip_static` pre-compressed JSON/GeoJSON,
immutable hashed assets, a Web Worker that parses the
payloads off the main thread, split vendor chunks, and PMTiles for detailed geometry.

## Security checklist

- Keep `.env` out of git; use `.env.prod.example` only as a template.
- Set `ALLOWED_ORIGINS=https://your-domain` before deploy.
- Keep only ports 80/443 open to the internet; `api` and `web` are loopback-bound by compose.
- Verify `curl -I https://your-domain` shows `Strict-Transport-Security`,
  `Content-Security-Policy`, `X-Content-Type-Options`, and `Permissions-Policy`.
- Run `make verify-csp` after setting analytics/Sentry domains, because external telemetry origins
  must be added to nginx `connect-src`.
- Run `make prod-check` after every scoring/data rebuild; it fails if rank-band calibration is
  skipped.
