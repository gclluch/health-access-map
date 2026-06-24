/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Base URL for the dynamic FastAPI backend. Empty = same-origin /api (dev proxy / co-deploy);
  // set to the API origin (e.g. https://api.example.org) when the API is on another host.
  readonly VITE_API_BASE?: string;
  // Optional, env-gated observability (see lib/observability.ts). Unset = no telemetry.
  readonly VITE_SENTRY_DSN?: string;
  readonly VITE_ANALYTICS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
