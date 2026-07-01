/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Optional, env-gated observability (see lib/observability.ts). Unset = no telemetry.
  readonly VITE_SENTRY_DSN?: string;
  readonly VITE_ANALYTICS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
