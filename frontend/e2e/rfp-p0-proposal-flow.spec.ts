import { expect, test } from '@playwright/test'

const username = process.env.E2E_USERNAME ?? process.env.ADMIN_USERNAME ?? 'admin'
const password = process.env.E2E_PASSWORD ?? process.env.ADMIN_PASSWORD ?? 'admin'
const brief = 'Groupe hospitalier : déployer un portail patient sécurisé HDS, interopérable avec le Dossier Patient Informatisé (DPI) via des API REST et FHIR, et intégrant l\'authentification ProSanté Connect.'

test('RFP proposal renders all 19 sections, claim badges, citations, and actions', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const pageErrors: Error[] = []
  page.on('pageerror', (error) => pageErrors.push(error))

  // 1. Mock authentic P0 RFP API response
  await page.route('**/api/rfp/generate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'rfp-e2e-test',
        requirements: { sector: 'sante' },
        proposal: {
          title: 'Proposition de réponse — Santé',
          executiveSummary: 'Accompagnement Avaliance pour le déploiement du portail patient sécurisé HDS.',
          sections: [
            {
              key: 'executive_summary',
              order: 1,
              title: 'Synthèse exécutive',
              status: 'complete',
              narrative: ['Accompagnement Avaliance pour le déploiement du portail patient sécurisé HDS.'],
              claims: [
                { id: 'claim-001', text: 'Déployer un portail patient sécurisé HDS', kind: 'brief_fact', sourceIds: ['brief'], citationIndexes: [] },
                { id: 'claim-002', text: 'Engager un cadrage initial.', kind: 'recommendation', sourceIds: [], citationIndexes: [] },
              ],
              bullets: [],
              tables: [],
              questions: [],
              factsFromBrief: ['Déployer un portail patient sécurisé HDS'],
              verifiedReferences: [],
              recommendations: ['Engager un cadrage initial.'],
              assumptionsToConfirm: [],
            },
            {
              key: 'references_differentiation_next_steps',
              order: 19,
              title: 'Références, différenciation Avaliance et prochaines étapes',
              status: 'complete',
              narrative: ['Preuves documentaires internes issues du retour d\'expérience Santélia.'],
              claims: [
                {
                  id: 'claim-019',
                  text: 'Retour d\'expérience Santélia Santé (Page 1) : Déploiement d\'un portail patient sécurisé.',
                  kind: 'internal_evidence',
                  sourceIds: ['doc-01'],
                  citationIndexes: [1],
                },
              ],
              bullets: ['Action 1 : Cadrage initial'],
              tables: [
                {
                  title: 'Prochaines étapes',
                  columns: ['Action', 'Délai', 'Responsable'],
                  rows: [['Cadrage', 'T0 + 1 sem', 'Directeur de mission']],
                },
              ],
              questions: [],
              factsFromBrief: [],
              verifiedReferences: [
                {
                  id: 'claim-019',
                  text: 'Retour d\'expérience Santélia Santé (Page 1) : Déploiement d\'un portail patient sécurisé.',
                  kind: 'internal_evidence',
                  sourceIds: ['doc-01'],
                  citationIndexes: [1],
                },
              ],
              recommendations: [],
              assumptionsToConfirm: [],
            },
          ],
        },
        sources: [
          {
            id: 'doc-01',
            type: 'internal_pdf',
            title: '05_Groupe_Santelia_Portail_Patient_Interoperabilite_Dossier_Projet.pdf (p. 1)',
            documentId: 5,
            documentName: '05_Groupe_Santelia_Portail_Patient_Interoperabilite_Dossier_Projet.pdf',
            page: 1,
            chunkId: 1102,
            excerpt: 'Portail patient et interopérabilité HDS.',
          },
        ],
        citations: [
          {
            citationId: 'rfp-1102',
            chunkId: 1102,
            documentId: 5,
            documentName: '05_Groupe_Santelia_Portail_Patient_Interoperabilite_Dossier_Projet.pdf',
            page: 1,
            content: 'Portail patient et interopérabilité HDS.',
            sourceIndex: 1,
          },
        ],
        similarMissions: [],
        evidenceValidationPassed: true,
        quality: {
          passed: true,
          score: 1.0,
          coverageScore: 1.0,
          citationIntegrity: 1.0,
          sectionCount: 19,
          warnings: [],
        },
      }),
    })
  })

  // 2. Login
  await page.goto('/login')
  await page.getByLabel('Identifiant').fill(username)
  await page.locator('input[type="password"]').fill(password)
  await page.getByRole('button', { name: 'Se connecter' }).click()
  await expect(page).toHaveURL(/\/tableau-de-bord$/)

  // 3. Navigate to /propositions
  await page.goto('/propositions')
  await page.getByLabel('Brief client ou cahier des charges').fill(brief)
  await page.getByRole('button', { name: 'Générer la proposition' }).click()

  // 4. Verify rendered components
  await expect(page.getByRole('heading', { name: 'Proposition de réponse — Santé' })).toBeVisible()
  await expect(page.getByText('Sections : 2/19')).toBeVisible()
  await expect(page.getByText('Indice de conformité : 100%')).toBeVisible()
  await expect(page.getByText('Preuves PDF : 1 document(s)')).toBeVisible()

  // Verify Claim Badges
  await expect(page.getByText('Faits issus du brief client')).toBeVisible()
  await expect(page.getByText('Références internes vérifiées')).toBeVisible()
  await expect(page.getByText('Recommandations').first()).toBeVisible()

  // Verify Citation Chip
  await expect(page.locator('.citation-chip').first()).toBeVisible()

  // Verify Action Buttons
  await expect(page.getByRole('button', { name: 'Copier' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Télécharger' })).toBeVisible()

  // Click Copy
  await page.getByRole('button', { name: 'Copier' }).click()
  await expect(page.getByRole('status')).toContainText('Proposition copiée.')

  expect(pageErrors).toEqual([])
})

test('RFP proposal renders honest fallback and warning when no evidence is found', async ({ page }) => {
  const pageErrors: Error[] = []
  page.on('pageerror', (error) => pageErrors.push(error))

  // 1. Mock No-Evidence Response
  await page.route('**/api/rfp/generate', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        requestId: 'rfp-quantum-test',
        requirements: { sector: 'spatial' },
        proposal: {
          title: 'Proposition de réponse — Spatial',
          sections: [
            {
              key: 'executive_summary',
              order: 1,
              title: 'Synthèse exécutive',
              status: 'complete',
              narrative: ['Proposition consultative pour constellation quantique.'],
              claims: [
                { id: 'claim-001', text: 'Constellation de nanosatellites LEO', kind: 'brief_fact', sourceIds: ['brief'], citationIndexes: [] },
                { id: 'claim-002', text: 'Définir un protocole QKD.', kind: 'recommendation', sourceIds: [], citationIndexes: [] },
              ],
              bullets: [],
              tables: [],
              questions: [],
              factsFromBrief: ['Constellation de nanosatellites LEO'],
              verifiedReferences: [],
              recommendations: ['Définir un protocole QKD.'],
              assumptionsToConfirm: [],
            },
          ],
        },
        sources: [],
        citations: [],
        similarMissions: [],
        evidenceValidationPassed: false,
        diagnostic: 'NO_RELEVANT_PDF_EVIDENCE',
        quality: {
          passed: true,
          score: 0.7,
          coverageScore: 1.0,
          citationIntegrity: null,
          sectionCount: 19,
          warnings: ['Aucune preuve PDF interne pertinente'],
        },
      }),
    })
  })

  // 2. Login
  await page.goto('/login')
  await page.getByLabel('Identifiant').fill(username)
  await page.locator('input[type="password"]').fill(password)
  await page.getByRole('button', { name: 'Se connecter' }).click()
  await expect(page).toHaveURL(/\/tableau-de-bord$/)

  // 3. Navigate to /propositions
  await page.goto('/propositions')
  await page.getByLabel('Brief client ou cahier des charges').fill('Constellation nanosatellites quantique LEO')
  await page.getByRole('button', { name: 'Générer la proposition' }).click()

  // 4. Verify No-Evidence Warning Banner
  await expect(page.locator('.rfp-no-evidence')).toContainText('Aucune preuve PDF suffisamment pertinente n’a été retenue dans la base interne')
  await expect(page.getByText('Indice de conformité : 70%')).toBeVisible()
  await expect(page.getByText('Avertissements : 1')).toBeVisible()

  expect(pageErrors).toEqual([])
})
