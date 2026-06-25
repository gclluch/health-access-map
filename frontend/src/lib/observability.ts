// Dependency-free, env-gated observability. Both hooks no-op unless their env var is set, so
// there is zero overhead and zero third-party code in the default build. Wire real providers
// (Sentry, Plausible, etc.) behind these same env vars without touching call sites.
//
//   VITE_SENTRY_DSN     -> POST uncaught errors / rejections as JSON
//   VITE_ANALYTICS_URL  -> sendBeacon privacy-light usage events (no PII, no cookies)

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN;
const ANALYTICS_URL = import.meta.env.VITE_ANALYTICS_URL;

function report(kind: string, message: string, extra?: Record<string, unknown>) {
  if (!SENTRY_DSN) return;
  try {
    const body = JSON.stringify({ kind, message, extra, ua: navigator.userAgent, ts: Date.now(), url: location.href });
    // keepalive lets the request survive a page teardown after a fatal error
    fetch(SENTRY_DSN, { method: 'POST', body, headers: { 'content-type': 'application/json' }, keepalive: true }).catch(() => {});
  } catch {
    /* never let telemetry throw into the app */
  }
}

// Report a caught error (e.g. from a React error boundary). No-ops unless VITE_SENTRY_DSN is set.
export function reportError(message: string, extra?: Record<string, unknown>) {
  report('react-error', message, extra);
}

// Lightweight product analytics: which features get used (the audit's "you don't know what users do").
export function track(event: string, props?: Record<string, unknown>) {
  if (!ANALYTICS_URL) return;
  try {
    const payload = JSON.stringify({ event, props, ts: Date.now() });
    if (navigator.sendBeacon) navigator.sendBeacon(ANALYTICS_URL, payload);
    else fetch(ANALYTICS_URL, { method: 'POST', body: payload, keepalive: true }).catch(() => {});
  } catch {
    /* swallow */
  }
}

let installed = false;
export function initObservability() {
  if (installed) return;
  installed = true;
  if (SENTRY_DSN) {
    window.addEventListener('error', (e) => report('error', e.message, { stack: e.error?.stack }));
    window.addEventListener('unhandledrejection', (e) =>
      report('unhandledrejection', String(e.reason?.message ?? e.reason)),
    );
  }
  track('app_loaded');
}
