import { defineConfig } from '@playwright/test';

// The user check: walks each flow in docs/feature-map.md against a local
// ResumeRadar with every outside service faked (serve.py). Nothing here
// reaches Claude, Resend, Beehiiv, a real Redis or the live site.
const PORT = Number(process.env.USER_CHECK_PORT || 5055);
const PYTHON = process.env.PYTHON || '../../.venv/bin/python';

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.ts$/,
  // One worker: the flows share one local server, and its per-visitor limits
  // (for example 5 cover letters a day) count every test.
  workers: 1,
  fullyParallel: false,
  // A flaky check is fixed, not retried (shola-project-run-rules).
  retries: 0,
  forbidOnly: !!process.env.CI,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: process.env.CI ? [['list'], ['github']] : 'list',
  outputDir: './test-results',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'off',
    screenshot: 'only-on-failure',
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  projects: [
    { name: 'phone-375', use: { viewport: { width: 375, height: 812 }, hasTouch: true } },
    { name: 'desktop-1280', use: { viewport: { width: 1280, height: 800 } } },
  ],
  webServer: {
    command: `${PYTHON} serve.py ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    // Always a fresh server, so its private Redis and limits start empty.
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: 'ignore',
    stderr: 'pipe',
    // SIGTERM, not the default SIGKILL, so serve.py stops its Redis and
    // removes its temporary folder.
    gracefulShutdown: { signal: 'SIGTERM', timeout: 5000 },
  },
});
