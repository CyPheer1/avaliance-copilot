import { expect, test } from '@playwright/test'
import { writeFileSync } from 'node:fs'

const username = process.env.E2E_USERNAME ?? process.env.ADMIN_USERNAME ?? 'admin'
const password = process.env.E2E_PASSWORD ?? process.env.ADMIN_PASSWORD ?? 'admin'
const brief = "Une institution financière souhaite migrer son architecture batch vers une plateforme temps réel basée sur Apache Kafka et Java. L'objectif est de traiter 15 000 événements par seconde avec une latence p95 inférieure à 200 ms pour l'évaluation des transactions de paiement instantané."
const responseArtifact = process.env.RFP_E2E_RESPONSE_ARTIFACT ?? 'test-results/rfp-banking-live-response.json'

function proposalText(payload: any): string {
  const proposal = payload.proposal ?? {}
  return [
    proposal.title,
    proposal.executive_summary,
    ...(proposal.sections ?? []).flatMap((section: any) => [
      section.title,
      section.body,
      ...(section.bullets ?? []).map((bullet: any) => bullet.text),
      ...(section.questions ?? []),
      ...(section.assumptions ?? []),
    ]),
  ].filter(Boolean).join('\n')
}

test('[LIVE-STRICT] authenticated banking proposal has canonical quality and provenance', async ({ page }) => {
  test.skip(process.env.E2E_REAL_STACK !== 'true', 'Requires the live Compose stack')
  test.setTimeout(600_000)

  let status: number | undefined
  let payload: any
  const pageErrors: Error[] = []
  page.on('pageerror', (error) => pageErrors.push(error))

  await page.goto('/login')
  await page.getByLabel('Identifiant').fill(username)
  await page.locator('input[type="password"]').fill(password)
  await page.getByRole('button', { name: 'Se connecter' }).click()
  await expect(page).toHaveURL(/\/tableau-de-bord$/)

  await page.goto('/propositions')
  await page.getByLabel('Brief client ou cahier des charges').fill(brief)
  await page.getByRole('button', { name: 'Paramètres avancés' }).click()
  await page.getByLabel('Secteur').fill('banque')
  await page.getByLabel('Mode de génération').selectOption('standard')

  const responsePromise = page.waitForResponse((response) => response.url().includes('/api/rfp/generate') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Générer la proposition' }).click()
  const response = await responsePromise
  status = response.status()
  payload = await response.json()
  writeFileSync(responseArtifact, JSON.stringify({ status, brief, payload }, null, 2))

  expect(status).toBe(200)
  expect(payload.mode).toBe('standard')
  expect(payload.status).toBe('completed')
  expect(payload.quality?.passed).toBe(true)
  expect(payload.evidenceValidationPassed ?? payload.evidence_validation_passed).toBe(true)
  expect(payload.quality?.warnings ?? []).toEqual([])

  const sections = payload.proposal?.sections ?? []
  expect(sections).toHaveLength(6)
  expect(sections.map((section: any) => section.order)).toEqual([1, 2, 3, 4, 5, 6])

  const text = proposalText(payload)
  expect(text).toContain('15 000')
  expect(text).toMatch(/200\s*ms/i)
  expect(text).not.toMatch(/\b92\s*%|\b19\s*heures|\b65\s*%|\b6\s*mois/i)
  expect(text).not.toMatch(/certificat(?:s)?\s+IoT|IoT.*certificat/i)

  const citedIds = new Set<string>([...text.matchAll(/\[(pdf-\d+)\]/gi)].map((match) => match[1].toLowerCase()))
  const structuredIds = new Set<string>(sections.flatMap((section: any) => (section.evidence ?? []).map((evidence: any) => evidence.id?.toLowerCase()).filter(Boolean)))
  const sourceRegister = payload.annexes?.sourceRegister ?? payload.annexes?.source_register ?? []
  const registeredIds = new Set<string>(sourceRegister.map((source: any) => (source.sourceId ?? source.source_id)?.toLowerCase()).filter(Boolean))
  const allCitedIds = new Set([...citedIds, ...structuredIds])

  expect(allCitedIds.size).toBeGreaterThan(0)
  expect([...allCitedIds].every((id) => registeredIds.has(id))).toBe(true)
  expect([...registeredIds].every((id) => allCitedIds.has(id))).toBe(true)
  expect(sourceRegister.every((source: any) => (source.quote ?? '').trim().length > 0 && (source.documentName ?? source.document_name ?? '').trim().length > 0 && (source.chunkId ?? source.chunk_id) != null)).toBe(true)

  await expect(page.locator('.rfp-document')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('Sections : 6/6')).toBeVisible()
  expect(pageErrors).toEqual([])
})
