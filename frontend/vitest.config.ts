/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Two kinds of unit test share this config. `*.test.ts` covers the pure scoring/format/color
// logic and needs no DOM, so it stays on the faster `node` environment; `*.test.tsx` renders
// components with Testing Library and gets `jsdom` via the glob below. The Playwright e2e suite
// lives under e2e/ and is run separately (npm run test:e2e), so it is excluded here.
//
// Component tests deliberately stop at the map: deck.gl needs a real GL context, which is what
// the e2e suite (and only the e2e suite) provides.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
    environmentMatchGlobs: [['src/**/*.test.tsx', 'jsdom']],
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test/setup.ts'],
    exclude: ['e2e/**', 'node_modules/**'],
    restoreMocks: true,
  },
});
