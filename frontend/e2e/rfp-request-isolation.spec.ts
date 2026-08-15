import { expect, test } from '@playwright/test'

const username = process.env.E2E_USERNAME ?? process.env.ADMIN_USERNAME
const password = process.env.E2E_PASSWORD ?? process.env.ADMIN_PASSWORD
const nis2Brief = 'NIS2 : segmenter le réseau, généraliser MFA, centraliser les journaux dans un SIEM et préparer un exercice de reprise.'
const dataBrief = "Nous consolidons quatorze bases de données afin de produire des KPI commerciaux unifiés et des rapports d'attrition clients. Databricks est une option à confirmer."
const forbidden = /NIS2|segmentation|MFA|SIEM|actifs critiques|échéance réglementaire|exercice de reprise/i

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByLabel('Identifiant').fill(username!)
  await page.locator('input[type="password"]').fill(password!)
  await page.getByRole('button', { name: 'Se connecter' }).click()
  await expect(page).toHaveURL(/\/tableau-de-bord$/)
}

test('a later data brief replaces the earlier NIS2 proposal', async ({ page }) => {
  test.skip(!username || !password, 'Set E2E_USERNAME and E2E_PASSWORD.')
  await login(page)
  await page.goto('/propositions')

  const requests: string[] = []
  await page.route('**/api/rfp/generate', async (route) => {
    const body = route.request().postDataJSON() as { requestId: string; description: string }
    requests.push(body.requestId)
    const isData = body.description === dataBrief
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: body.requestId,
        requirements: {},
        proposal: {
          title: 'Proposition de réponse',
          sections: [{
            key: 'summary', title: 'Synthèse exécutive',
            factsFromBrief: [body.description], verifiedReferences: [], recommendations: [], assumptionsToConfirm: [], tables: [],
          }],
        },
        citations: [], similarMissions: [], evidenceValidationPassed: false,
        diagnostic: isData ? 'NO_CLAIM_LEVEL_EVIDENCE' : null,
      }),
    })
  })

  const brief = page.getByLabel('Brief client ou cahier des charges')
  await brief.fill(nis2Brief)
  await page.getByRole('button', { name: 'Générer la proposition' }).click()
  await expect(page.locator('.rfp-result')).toContainText('NIS2')

  await brief.fill(dataBrief)
  await page.getByRole('button', { name: 'Générer la proposition' }).click()
  const result = page.locator('.rfp-result')
  await expect(result).toContainText('quatorze bases de données')
  await expect(result).not.toContainText(forbidden)
  await expect(result.locator('blockquote')).toHaveCount(0)
  await expect(result.locator('.reference-list')).toHaveCount(0)
  expect(requests).toHaveLength(2)
  expect(requests[0]).not.toBe(requests[1])
})
