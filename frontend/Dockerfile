# Frontend image: Vite build -> nginx static serve (gzip-static + cache headers + /api proxy).
# Build context is the REPO ROOT (the build needs frontend/public/{metrics.json,
# zcta_overview.geojson, zcta.pmtiles}, which are gitignored + produced by `make data`):
#   docker build -f frontend/Dockerfile -t ham-web .
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Empty default = same-origin /api (nginx proxies it). Set to an API origin for split deploys.
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE
# Build must succeed, and the data payloads must be present. metrics.json + the overview geojson
# are pre-compressed for nginx gzip_static; zcta.pmtiles is internally compressed and range-
# requested, so it is deliberately NOT gzipped. The old `... || true` swallowed both a failed
# build and a missing/failed gzip, so a broken image could ship silently.
RUN npm run build
RUN test -s dist/metrics.json && test -s dist/zcta_overview.geojson && test -s dist/zcta.pmtiles \
 && gzip -k -9 dist/metrics.json dist/zcta_overview.geojson

FROM nginx:alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
