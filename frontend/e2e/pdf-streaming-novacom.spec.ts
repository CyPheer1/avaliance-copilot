import { expect, test } from '@playwright/test'
import { writeFile } from 'node:fs/promises'

test.use({ trace: 'on' })

const username = process.env.E2E_USERNAME ?? process.env.ADMIN_USERNAME
const password = process.env.E2E_PASSWORD ?? process.env.ADMIN_PASSWORD
const novacomQuery = 'Qui a pris en charge la partie flux temps réel dans le projet Novacom Télécom (programme HORIZON DATA) ?'

test('PDF-only Novacom search streams grounded answer and PDF sources only', async ({ page, request }, testInfo) => {
  test.skip(!username || !password, 'Set E2E credentials in the root .env file.')

  const consoleErrors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })

  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window)
    ;(window as typeof window & { __streamFetchCalls?: Array<{ url: string; startedAt: number; resolvedAt?: number }> }).__streamFetchCalls = []
    window.fetch = async (...args) => {
      const startedAt = performance.now()
      const url = typeof args[0] === 'string' ? args[0] : args[0] instanceof Request ? args[0].url : String(args[0])
      const entry = { url, startedAt }
      ;(window as typeof window & { __streamFetchCalls: Array<{ url: string; startedAt: number; resolvedAt?: number }> }).__streamFetchCalls.push(entry)
      const response = await originalFetch(...args)
      entry.resolvedAt = performance.now()
      return response
    }
  })

  await expect.poll(async () => {
    try {
      return (await request.get('http://127.0.0.1:8080/actuator/health')).ok()
    } catch {
      return false
    }
  }, { timeout: 60_000 }).toBeTruthy()

  await page.goto('/login')
  await page.getByLabel('Identifiant').fill(username!)
  await page.locator('input[type="password"]').fill(password!)
  await page.getByRole('button', { name: 'Se connecter' }).click()
  await expect(page).toHaveURL(/\/recherche$/)

  await page.getByLabel('Votre question').fill(novacomQuery)
  const streamResponsePromise = page.waitForResponse((response) => response.url().includes('/api/search/stream') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Rechercher' }).click()
  const streamResponse = await streamResponsePromise
  expect(streamResponse.ok()).toBeTruthy()

  await expect(page.getByText('Réponse sourcée', { exact: true })).toBeVisible()
  await expect(page.locator('.stream-answer')).toContainText('Pauline Vasseur')
  await expect(page.locator('.stream-answer')).toContainText('Ingénierie data')
  await expect(page.locator('.stream-answer')).toContainText('flux temps réel')

  const sources = page.locator('.source-card')
  await expect(sources.first()).toBeVisible()
  await expect(sources.first()).toContainText('02_Novacom_Telecom_Plateforme_Data_Retention_Bilan_Mission.pdf')
  await expect(sources.first()).toContainText('Page physique 13')
  await expect(sources.first()).toContainText(/Chunk \d+/)
  await expect(sources.first()).toContainText('Voir dans le document')
  await expect(sources).not.toContainText('MISSION')

  const citationMarkers = page.locator('.stream-answer .citation-chip')
  await expect(citationMarkers.first()).toBeVisible()
  const markerNumbers = await citationMarkers.allTextContents()
  const sourceNumbers = await sources.locator('.source-card__number').allTextContents()
  for (const marker of markerNumbers) expect(sourceNumbers).toContain(marker)

  const titles = await sources.locator('h3').allTextContents()
  expect(new Set(titles).size).toBe(titles.length)

  await expect.poll(async () => page.evaluate(() => ({
    metrics: (window as typeof window & { __avalianceStreamMetrics?: Record<string, number> }).__avalianceStreamMetrics ?? {},
    fetchCalls: (window as typeof window & { __streamFetchCalls?: Array<{ url: string; startedAt: number; resolvedAt?: number }> }).__streamFetchCalls ?? [],
    answerText: document.querySelector('.stream-answer')?.textContent ?? '',
    stateText: document.querySelector('.result-summary h2')?.textContent ?? '',
  })), { timeout: 30_000 }).toMatchObject({
    stateText: 'Réponse sourcée',
  })

  const timing = await page.evaluate(() => ({
    metrics: (window as typeof window & { __avalianceStreamMetrics?: Record<string, number> }).__avalianceStreamMetrics ?? {},
    fetchCalls: (window as typeof window & { __streamFetchCalls?: Array<{ url: string; startedAt: number; resolvedAt?: number }> }).__streamFetchCalls ?? [],
    answerText: document.querySelector('.stream-answer')?.textContent ?? '',
  }))

  const streamFetch = timing.fetchCalls.find((entry) => entry.url.includes('/api/search/stream'))
  expect(streamFetch).toBeDefined()
  expect(timing.metrics['stream-first-byte']).toBeGreaterThan(0)
  expect(timing.metrics['firstTokenRenderedMs']).toBeGreaterThan(0)
  expect(timing.metrics['stream-total']).toBeGreaterThan(timing.metrics['stream-first-byte'])
  expect(timing.metrics['stream-total']).toBeGreaterThan(timing.metrics['firstTokenRenderedMs'])
  expect(timing.answerText).toContain('Pauline Vasseur')
  expect((streamFetch!.resolvedAt ?? 0) - streamFetch!.startedAt).toBeGreaterThan(0)
  expect(timing.metrics['stream-first-byte']).toBeGreaterThanOrEqual(Math.floor((streamFetch!.resolvedAt ?? 0) - streamFetch!.startedAt))

  await page.screenshot({ path: testInfo.outputPath('pdf-streaming-novacom.png'), fullPage: true })
  await writeFile(testInfo.outputPath('console-errors.json'), JSON.stringify(consoleErrors, null, 2), 'utf-8')
  await writeFile(testInfo.outputPath('stream-timing.json'), JSON.stringify({ metrics: timing.metrics, streamFetch, answerText: timing.answerText }, null, 2), 'utf-8')
})
