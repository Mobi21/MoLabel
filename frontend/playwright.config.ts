import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { defineConfig, devices } from '@playwright/test'
import { API_URL, WEB_PORT, WEB_URL } from './e2e/env'

// Workers inherit the runner's environment, so the run shares one folder.
process.env.MOLABEL_E2E_ROOT ??= mkdtempSync(join(tmpdir(), 'molabel-e2e-'))

export default defineConfig({
  testDir: './e2e',
  testMatch: '*.e2e.ts',
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  timeout: 60_000,
  reporter: [['list']],
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL: WEB_URL,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
  webServer: {
    command: `npm run build && npx vite preview --host 127.0.0.1 --strictPort --port ${String(WEB_PORT)}`,
    url: WEB_URL,
    env: { MOLABEL_API_URL: API_URL },
    reuseExistingServer: false,
    timeout: 180_000,
  },
})
