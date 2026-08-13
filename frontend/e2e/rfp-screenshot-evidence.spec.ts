import { expect, test } from '@playwright/test'

const username = process.env.E2E_USERNAME ?? process.env.ADMIN_USERNAME
const password = process.env.E2E_PASSWORD ?? process.env.ADMIN_PASSWORD
const brief = 'Groupe de transport et logistique, 18 sites en France, soumis à la directive NIS2. Nous devons segmenter le réseau, généraliser le second facteur d’authentification, centraliser les journaux dans un SIEM, ouvrir une astreinte de supervision 24 h/24 et éprouver notre plan de reprise d’activité. Échéance réglementaire : fin d’année.'

test('captures real desktop and mobile RFP screens', async ({ page }) => {
  test.skip(!username || !password, 'Set E2E_USERNAME/E2E_PASSWORD or ADMIN_USERNAME/ADMIN_PASSWORD.')

  await page.goto('/login')
  await page.getByLabel('Identifiant').fill(username!)
  await page.locator('input[type="password"]').fill(password!)
  await page.getByRole('button', { name: 'Se connecter' }).click()
  await expect(page).toHaveURL(/\/tableau-de-bord$/)

  await page.goto('/propositions')
  await expect(page).toHaveURL(/\/propositions$/)
  await page.getByLabel('Brief client ou cahier des charges').fill(brief)
  const responsePromise = page.waitForResponse((response) => response.url().includes('/api/rfp/generate') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Générer la proposition' }).click()
  expect((await responsePromise).ok()).toBeTruthy()
  await expect(page.getByRole('heading', { name: 'Proposition de réponse' })).toBeVisible()

  await page.setViewportSize({ width: 1280, height: 960 })
  await page.screenshot({ path: '/home/ubuntu/apps/avaliance-copilot/benchmarks/rfp-desktop-1280.png', fullPage: true })

  await page.setViewportSize({ width: 375, height: 812 })
  await page.screenshot({ path: '/home/ubuntu/apps/avaliance-copilot/benchmarks/rfp-mobile-375.png', fullPage: true })
})
