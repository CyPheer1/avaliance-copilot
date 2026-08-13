import { expect, test } from '@playwright/test'

const username = process.env.E2E_USERNAME ?? process.env.ADMIN_USERNAME
const password = process.env.E2E_PASSWORD ?? process.env.ADMIN_PASSWORD
const brief = 'Groupe de transport et logistique, 18 sites en France, soumis à la directive NIS2. Nous devons segmenter le réseau, généraliser le second facteur d’authentification, centraliser les journaux dans un SIEM, ouvrir une astreinte de supervision 24 h/24 et éprouver notre plan de reprise d’activité. Échéance réglementaire : fin d’année.'

test('RFP malformed response remains controlled and retryable', async ({ page }) => {
  test.skip(!username || !password, 'Set E2E_USERNAME and E2E_PASSWORD.')
  const pageErrors: Error[] = []
  page.on('pageerror', (error) => pageErrors.push(error))

  await page.goto('/login')
  await page.getByLabel('Identifiant').fill(username!)
  await page.locator('input[type="password"]').fill(password!)
  await page.getByRole('button', { name: 'Se connecter' }).click()
  await expect(page).toHaveURL(/\/tableau-de-bord$/)

  await page.route('**/api/rfp/generate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ requirements: {}, proposal: {}, citations: [], similarMissions: [] }),
    })
  })
  await page.goto('/propositions')
  await page.getByLabel('Brief client ou cahier des charges').fill(brief)
  await page.getByRole('button', { name: 'Générer la proposition' }).click()

  await expect(page.getByRole('alert')).toContainText('réponse de proposition est invalide ou incomplète')
  await expect(page.getByRole('button', { name: 'Réessayer' })).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Navigation principale' })).toBeVisible()
  expect(pageErrors).toEqual([])
})

test('RFP legacy response renders without crashing the application', async ({ page }) => {
  test.skip(!username || !password, 'Set E2E_USERNAME and E2E_PASSWORD.')
  const pageErrors: Error[] = []
  page.on('pageerror', (error) => pageErrors.push(error))

  await page.goto('/login')
  await page.getByLabel('Identifiant').fill(username!)
  await page.locator('input[type="password"]').fill(password!)
  await page.getByRole('button', { name: 'Se connecter' }).click()
  await expect(page).toHaveURL(/\/tableau-de-bord$/)

  await page.route('**/api/rfp/generate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        rfpStructure: '# Synthèse exécutive\n\nUne proposition lisible.\n\n## Périmètre\n\n- Segmentation réseau\n- Supervision SIEM\n\n| Phase | Livrable |\n| --- | --- |\n| Cadrage | Feuille de route |',
        similarMissions: [],
      }),
    })
  })
  await page.goto('/propositions')
  await page.getByLabel('Brief client ou cahier des charges').fill(brief)
  await page.getByRole('button', { name: 'Générer la proposition' }).click()

  const document = page.locator('.markdown-document')
  await expect(document.getByRole('heading', { name: 'Synthèse exécutive' })).toBeVisible()
  await expect(document.getByRole('heading', { name: 'Périmètre' })).toBeVisible()
  await expect(document.getByText('Segmentation réseau')).toBeVisible()
  await expect(document.locator('table')).toBeVisible()
  await expect(page.locator('.rfp-statement--fact')).toHaveCount(0)
  await expect(page.getByText('Proposition héritée')).toHaveCount(0)
  await expect(page.getByRole('navigation', { name: 'Navigation principale' })).toBeVisible()
  expect(pageErrors).toEqual([])
})
