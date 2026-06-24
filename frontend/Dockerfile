# Frontend image: Vite build -> nginx static serve (gzip-static + cache headers + /api proxy).
# Build context is the REPO ROOT (the build needs frontend/public/{metrics.json,zcta.geojson},
# which are gitignored + produced by `make data`):
#   docker build -f frontend/Dockerfile -t ham-web .
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Empty default = same-origin /api (nginx proxies it). Set to an API origin for split deploys.
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build \
 && gzip -k -9 dist/metrics.json dist/zcta.geojson 2>/dev/null || true

FROM nginx:alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
