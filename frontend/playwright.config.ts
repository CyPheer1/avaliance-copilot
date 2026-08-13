import { defineConfig } from '@playwright/test'
import { config as loadEnv } from 'dotenv'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDirectory = dirname(fileURLToPath(import.meta.url))
loadEnv({ path: resolve(frontendDirectory, '../.env'), quiet: true })

const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173'
const usesExternalServer = !/^https?:\/\/127\.0\.0\.1:5173$/i.test(baseURL)

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  timeout: 1_200_000,
  expect: { timeout: 20_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: usesExternalServer ? undefined : {
    command: 'npm run dev -- --host 127.0.0.1',
    cwd: frontendDirectory,
    url: 'http://127.0.0.1:5173/login',
    reuseExistingServer: true,
    timeout: 30_000,
  },
})