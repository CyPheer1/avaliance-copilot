import { expect, test } from '@playwright/test'

const username = process.env.E2E_USERNAME ?? process.env.ADMIN_USERNAME
const password = process.env.E2E_PASSWORD ?? process.env.ADMIN_PASSWORD

test.use({ screenshot: 'on', trace: 'on', video: 'on' })

test('records the real browser login request and rendered dashboard', async ({ page }, testInfo) => {
  test.skip(!username || !password, 'Set E2E_USERNAME/E2E_PASSWORD or ADMIN_USERNAME/ADMIN_PASSWORD in .env.')

  const consoleErrors: string[] = []
  const pageErrors: string[] = []
  const requestFailures: string[] = []
  const requests: Array<{
    url: string
    method: string
    headers: Record<string, string>
  }> = []
  const responses: Array<{
    url: string
    status: number
    headers: Record<string, string>
    timing: { startTime: number; domainLookupStart: number; domainLookupEnd: number; connectStart: number; secureConnectionStart: number; connectEnd: number; requestStart: number; responseStart: number; responseEnd: number }
  }> = []

  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('pageerror', (error) => pageErrors.push(error.stack ?? error.message))
  page.on('requestfailed', (request) => requestFailures.push(`${request.method()} ${request.url()} ${request.failure()?.errorText ?? 'unknown failure'}`))
  page.on('request', (request) => {
    if (request.url().includes('/auth/login')) {
      requests.push({ url: request.url(), method: request.method(), headers: request.headers() })
    }
  })
  page.on('response', (response) => {
    if (response.url().includes('/auth/login')) {
      const request = response.request()
      responses.push({
        url: response.url(),
        status: response.status(),
        headers: response.headers(),
        timing: request.timing(),
      })
    }
  })

  await page.goto('/login')
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('Identifiant').fill(username!)
  await page.locator('input[type="password"]').fill(password!)

  const loginResponse = page.waitForResponse((response) => response.url().includes('/auth/login') && response.request().method() === 'POST')
  await page.locator('button.login-submit').click()
  const response = await loginResponse

  expect(response.status()).toBe(200)
  await expect(page).toHaveURL(/\/tableau-de-bord$/)
  await expect(page.getByRole('heading', { name: "Vue d'ensemble" })).toBeVisible()
  await expect(page.locator('button.login-submit')).toHaveCount(0)

  const session = await page.evaluate(() => ({
    session: localStorage.getItem('avaliance-copilot-session'),
  }))
  expect(session.session).not.toBeNull()

  await page.screenshot({ path: testInfo.outputPath('dashboard-authenticated.png'), fullPage: true })
  await testInfo.attach('login-browser-evidence.json', {
    body: JSON.stringify({
      baseURL: testInfo.project.use.baseURL,
      finalURL: page.url(),
      consoleErrors,
      pageErrors,
      requestFailures,
      requests,
      responses,
      session: { stored: session.session !== null, length: session.session?.length ?? 0 },
      serviceWorker: await page.evaluate(() => navigator.serviceWorker?.getRegistrations().then((items) => items.map((item) => item.scope)) ?? []),
    }, null, 2),
    contentType: 'application/json',
  })
})
