import { defineConfig, devices } from '@playwright/test';

// Smoke-level e2e: boots the Vite dev server against a tiny fixture (e2e/make-fixture.mjs)
// and checks the app loads, renders chrome, and responds to interaction. SwiftShader gives
// headless Chromium a software WebGL context so deck.gl/MapLibre initialize in CI.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  // Every spec boots a deck.gl/MapLibre instance on SwiftShader's software GL. Past two at a
  // time they starve each other and time out waiting for a map that would render in a second
  // alone, so the cap is the renderer's, not the machine's.
  workers: 2,
  // The panels are lazy chunks, and the dev server serves them unbundled behind the map's own
  // module waterfall: 15s to first paint is normal here, not a hang. The 5s default turns that
  // into flake. Cost of the higher ceiling is that a genuine failure takes 15s to report.
  expect: { timeout: 15_000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        launchOptions: {
          args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader'],
        },
      },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
