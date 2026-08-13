import { expect, test } from '@playwright/test'

const username = process.env.E2E_USERNAME ?? process.env.ADMIN_USERNAME
const password = process.env.E2E_PASSWORD ?? process.env.ADMIN_PASSWORD

test.describe('login flow', () => {
  test('shows an authentication error and restores the form after a failed response', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Identifiant').fill('invalid-user')
    await page.locator('input[type="password"]').fill('invalid-password')
    await page.getByRole('button', { name: 'Se connecter' }).click()

    await expect(page.getByRole('alert')).toContainText('Invalid username or password')
    await expect(page.getByRole('button', { name: 'Se connecter' })).toBeEnabled()
    await expect(page).toHaveURL(/\/login$/)
  })

  test('shows a visible connection error and restores the form after a network failure', async ({ page }) => {
    await page.route('**/api/auth/login', (route) => route.abort('connectionrefused'))

    await page.goto('/login')
    await page.getByLabel('Identifiant').fill('network-check')
    await page.locator('input[type="password"]').fill('network-check')
    await page.locator('button.login-submit').click()

    await expect(page.getByRole('alert')).toContainText('Erreur de connexion : le serveur est injoignable.')
    await expect(page.locator('button.login-submit')).toBeEnabled()
    await expect(page).toHaveURL(/\/login$/)
  })

  test('shows a visible server error and restores the form after a 500 response', async ({ page }) => {
    await page.route('**/api/auth/login', (route) => route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ message: 'Erreur interne du serveur.' }) }))

    await page.goto('/login')
    await page.getByLabel('Identifiant').fill('server-check')
    await page.locator('input[type="password"]').fill('server-check')
    await page.locator('button.login-submit').click()

    await expect(page.getByRole('alert')).toContainText('Erreur interne du serveur.')
    await expect(page.locator('button.login-submit')).toBeEnabled()
    await expect(page).toHaveURL(/\/login$/)
  })

  test('prevents duplicate login requests while a submission is pending', async ({ page }) => {
    let loginRequests = 0
    await page.route('**/api/auth/login', async (route) => {
      loginRequests += 1
      await new Promise((resolve) => setTimeout(resolve, 1_000))
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Identifiant ou mot de passe incorrect.' }),
      })
    })

    await page.goto('/login')
    await page.getByLabel('Identifiant').fill('duplicate-check')
    await page.locator('input[type="password"]').fill('duplicate-check')
    const button = page.locator('button.login-submit')
    await button.click({ noWaitAfter: true })
    await expect(button).toBeDisabled()
    await page.locator('form.login-form').evaluate((form) => form.requestSubmit())
    await expect.poll(() => loginRequests).toBe(1)

    await expect(page.getByRole('alert')).toBeVisible()
    await expect(button).toBeEnabled()
  })


  test('times out a stalled login request and restores the form', async ({ page }) => {
    await page.route('**/api/auth/login', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 16_000))
      await route.fulfill({ status: 504, contentType: 'application/json', body: '{}' })
    })

    await page.goto('/login')
    await page.getByLabel('Identifiant').fill('timeout-check')
    await page.locator('input[type="password"]').fill('timeout-check')
    await page.getByRole('button', { name: 'Se connecter' }).click()

    await expect(page.getByRole('alert')).toContainText('Erreur de connexion : le serveur est injoignable ou la demande a expiré.', { timeout: 17_000 })
    await expect(page.getByRole('button', { name: 'Se connecter' })).toBeEnabled()
    await expect(page).toHaveURL(/\/login$/)
  })

  test('redirects to the dashboard only after a successful login response', async ({ page }) => {
    test.skip(!username || !password, 'Set E2E_USERNAME/E2E_PASSWORD or ADMIN_USERNAME/ADMIN_PASSWORD in .env.')

    await page.goto('/login')
    await page.getByLabel('Identifiant').fill(username!)
    await page.locator('input[type="password"]').fill(password!)
    const responsePromise = page.waitForResponse((response) => response.url().includes('/api/auth/login') && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Se connecter' }).click()

    const response = await responsePromise
    expect(response.ok()).toBeTruthy()
    await expect(page).toHaveURL(/\/tableau-de-bord$/)
  })
})
