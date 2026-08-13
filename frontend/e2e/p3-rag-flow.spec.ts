import { expect, test } from '@playwright/test'

const username = process.env.E2E_USERNAME ?? process.env.ADMIN_USERNAME
const password = process.env.E2E_PASSWORD ?? process.env.ADMIN_PASSWORD
const internalToken = process.env.INTERNAL_TOKEN

test('P3 delivers sourced search, guardrail, and similar missions', async ({ page, request }) => {
  test.skip(!username || !password || !internalToken, 'Set E2E credentials and INTERNAL_TOKEN in the root .env file.')

  await test.step('authenticate through Spring Security', async () => {
    await expect.poll(async () => {
      try {
        return (await request.get('http://127.0.0.1:8080/actuator/health')).ok()
      } catch {
        return false
      }
    }, {
      message: 'Spring Boot must be healthy before authentication',
      timeout: 60_000,
    }).toBeTruthy()
    await expect.poll(async () => {
      try {
        return (await request.get('http://127.0.0.1:8000/ready', {
          headers: { 'X-Internal-Token': internalToken! },
        })).ok()
      } catch {
        return false
      }
    }, {
      message: 'FastAPI must be ready before retrieval and generation',
      timeout: 180_000,
    }).toBeTruthy()
    await page.goto('/login')
    await page.getByLabel('Identifiant').fill(username!)
    await page.locator('input[type="password"]').fill(password!)
    const responsePromise = page.waitForResponse((response) => response.url().includes('/api/auth/login') && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Se connecter' }).click()
    const response = await responsePromise
    if (!response.ok()) await page.locator('input[type="password"]').fill('')
    expect(response.ok()).toBeTruthy()
    await expect(page).toHaveURL(/\/tableau-de-bord$/)
  })

  await test.step('return a grounded answer with citations and confidence', async () => {
    await page.getByRole('link', { name: 'Recherche' }).click()
    await expect(page).toHaveURL(/\/recherche$/)
    await page.getByLabel('Votre question').fill('Quelles technologies ont été utilisées pour les missions de migration cloud dans le secteur bancaire ?')
    const responsePromise = page.waitForResponse((response) => response.url().includes('/api/search') && response.request().method() === 'POST', { timeout: 660_000 })
    await page.getByRole('button', { name: 'Rechercher' }).click()
    const response = await responsePromise

    expect(response.ok()).toBeTruthy()
    await expect(page.getByText('Réponse sourcée', { exact: true })).toBeVisible()
    await expect(page.locator('.confidence-meter')).toContainText(/^Confiance \d+%$/)
    await expect(page.getByRole('tab', { name: /Sources/ })).toHaveAttribute('aria-selected', 'true')
    const firstSource = page.locator('.source-card').first()
    await expect(firstSource).toBeVisible()
    await expect(firstSource).toContainText(/Page physique \d+/)
    await firstSource.getByRole('button', { name: 'Voir dans le document' }).click()
    await expect(page.getByRole('tab', { name: 'Document' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator('.document-viewer, .document-viewer__state--error')).toBeVisible()
  })

  await test.step('refuse generation when filters leave no relevant source', async () => {
    await page.getByRole('button', { name: 'Affiner le corpus' }).click()
    await page.getByLabel('Année').fill('2030')
    await page.getByLabel('Votre question').fill('Quel retour d’expérience existe pour cette mission inexistante ?')
    const responsePromise = page.waitForResponse((response) => response.url().includes('/api/search') && response.request().method() === 'POST', { timeout: 60_000 })
    await page.getByRole('button', { name: 'Rechercher' }).click()
    const response = await responsePromise

    expect(response.ok()).toBeTruthy()
    await expect(page.getByText('Information insuffisante', { exact: true })).toBeVisible()
    await expect(page.getByText('Aucune preuve suffisamment pertinente n’a été trouvée dans le corpus pour répondre de manière fiable.')).toBeVisible()
  })

  await test.step('generate an RFP structure from comparable missions', async () => {
    await page.getByRole('link', { name: 'Propositions' }).click()
    await page.getByLabel('Besoin ou cahier des charges').fill('Moderniser une plateforme bancaire vers le cloud avec une chaîne DevOps sécurisée et observable.')
    await page.getByLabel('Secteur').fill('banque')
    await page.getByLabel('Type de mission').fill('migration cloud')
    const responsePromise = page.waitForResponse((response) => response.url().includes('/api/rfp/generate') && response.request().method() === 'POST', { timeout: 660_000 })
    await page.getByRole('button', { name: 'Identifier les références et structurer' }).click()
    const response = await responsePromise

    expect(response.ok()).toBeTruthy()
    await expect(page.getByText('Missions comparables', { exact: true })).toBeVisible()
    await expect(page.locator('.reference-item').first()).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Structure de proposition' })).toBeVisible()
    await expect(page.locator('.markdown-document')).not.toContainText('Information insuffisante')
  })
})