import { defineConfig } from '@playwright/test'

// Use the already-running Vite server by default. Opt in to a managed server
// with PLAYWRIGHT_START_SERVER=1; no API server or credentials are required.
const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173'

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 2,
  timeout: 30_000,
  expect: { timeout: 5_000 },
  outputDir: './test-results',
  reporter: [['list'], ['html', { open: 'never' }], ['json', { outputFile: 'test-results/results.json' }]],
  use: {
    baseURL,
    browserName: 'chromium',
    locale: 'en-GB',
    timezoneId: 'UTC',
    colorScheme: 'light',
    reducedMotion: 'reduce',
    serviceWorkers: 'block',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'phone-375x812', use: { viewport: { width: 375, height: 812 } } },
    { name: 'tablet-820x900', use: { viewport: { width: 820, height: 900 } } },
    { name: 'desktop-1440x900', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'laptop-1366x640', use: { viewport: { width: 1366, height: 640 } } },
  ],
  webServer: process.env.PLAYWRIGHT_START_SERVER === '1' ? {
    command: 'npm run dev -- --host localhost --port 5173 --strictPort',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
  } : undefined,
})