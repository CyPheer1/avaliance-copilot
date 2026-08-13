import { expect, test } from '@playwright/test'

const username = process.env.E2E_USERNAME ?? process.env.ADMIN_USERNAME
const password = process.env.E2E_PASSWORD ?? process.env.ADMIN_PASSWORD

test('keeps a verified citation event when done omits citations', async ({ page }) => {
  test.skip(!username || !password, 'Set E2E credentials in the root .env file.')

  await page.goto('/login')
  await page.getByLabel('Identifiant').fill(username!)
  await page.locator('input[type="password"]').fill(password!)
  await page.getByRole('button', { name: 'Se connecter' }).click()
  await expect(page).toHaveURL(/\/recherche$/)

  await page.route('**/api/search/stream', async (route) => {
    const citation = {
      citationId: 'req-regression:1284',
      requestId: 'req-regression',
      chunkId: 1284,
      missionId: 12,
      missionTitle: 'Novacom Télécom',
      documentId: 44,
      documentName: 'novacom-evidence.pdf',
      page: 13,
      corpusScope: 'PDF',
      content: 'Pauline Vasseur a pris en charge les flux temps réel.',
      score: 0.98,
      rrfScore: 0.12,
      relevanceScore: 0.98,
      sourceIndex: 1,
    }
    const sse = [
      'event: status\ndata: {"status":"retrieving"}\n',
      'event: status\ndata: {"status":"generating"}\n',
      'event: delta\ndata: {"token":"Pauline Vasseur a pris en charge les flux temps réel. [1]"}\n',
      'event: validation\ndata: {"passed":true}\n',
      `event: citation\ndata: ${JSON.stringify({ citations: [citation] })}\n`,
      'event: done\ndata: {"done":true,"citations":[],"confidence":0.98,"validationPassed":true}\n',
    ].join('\n')
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      headers: { 'cache-control': 'no-cache' },
      body: sse,
    })
  })

  await page.getByLabel('Votre question').fill('Qui a pris en charge les flux temps réel ?')
  await page.getByRole('button', { name: 'Rechercher' }).click()

  await expect(page.getByText('Réponse sourcée', { exact: true })).toBeVisible()
  await expect(page.locator('.stream-answer')).toContainText('Pauline Vasseur')
  await expect(page.locator('.citation-chip')).toHaveText('[1]')
  const source = page.locator('.source-card')
  await expect(source).toHaveCount(1)
  await expect(source).toContainText('novacom-evidence.pdf')
  await expect(source).toContainText('Page physique 13')
  await expect(source).toContainText('Chunk 1284')
  await expect(source).toContainText('Pauline Vasseur a pris en charge les flux temps réel.')
  await expect(source.getByRole('button', { name: 'Voir dans le document' })).toBeVisible()
})
