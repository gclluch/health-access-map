/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config';

// Unit tests cover the pure scoring/format/color logic (no DOM needed). The Playwright
// e2e suite lives under e2e/ and is run separately (npm run test:e2e), so it is excluded here.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    exclude: ['e2e/**', 'node_modules/**'],
  },
});
