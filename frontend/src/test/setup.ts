import { afterEach } from 'vitest';

// vitest applies setupFiles to every project file, but the `*.test.ts` unit specs deliberately run
// on the `node` environment (no DOM, and faster for pure scoring/format logic). Everything below
// is DOM-only, so bail out there rather than blowing up their collection.
if (typeof window !== 'undefined') {
  const { cleanup } = await import('@testing-library/react');

  // Testing Library only auto-registers this when vitest runs with `globals: true`; this suite
  // imports its helpers explicitly, so unmount between specs or the second render of a component
  // finds the first one still in the document.
  afterEach(cleanup);

  // jsdom ships no matchMedia. Report desktop width so components that branch on it render their
  // full layout; a spec that cares about the phone branch overrides this itself.
  window.matchMedia = ((query: string) => ({
    matches: query.includes('min-width'),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
