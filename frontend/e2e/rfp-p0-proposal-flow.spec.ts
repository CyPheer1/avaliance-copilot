import { expect, test } from '@playwright/test'

const username = process.env.E2E_USERNAME ?? process.env.ADMIN_USERNAME ?? 'admin'
const password = process.env.E2E_PASSWORD ?? process.env.ADMIN_PASSWORD ?? 'admin'
const brief = 'Groupe hospitalier : déployer un portail patient sécurisé HDS, interopérable avec le Dossier Patient Informatisé (DPI) via des API REST et FHIR, et intégrant l\'authentification ProSanté Connect.'

const canonical19Keys = [
  'executive_summary',
  'context_understanding',
  'stakes_and_problem',
  'objectives_and_outcomes',
  'scope_inclusions',
  'scope_exclusions',
  'functional_solution',
  'technical_architecture',
  'integrations_and_interfaces',
  'security_compliance_governance',
  'methodology_phases_deliverables',
  'planning_and_milestones',
  'team_and_governance',
  'testing_and_acceptance',
  'migration_deployment_reversibility',
  'change_management_training',
  'operations_and_support',
  'risks_assumptions_clarifications',
  'references_differentiation_next_steps',
]

const canonical19Titles: Record<string, string> = {
  executive_summary: 'Synthèse exécutive',
  context_understanding: 'Compréhension du contexte',
  stakes_and_problem: 'Enjeux et problème à résoudre',
  objectives_and_outcomes: 'Objectifs et résultats attendus',
  scope_inclusions: 'Périmètre inclus',
  scope_exclusions: 'Périmètre exclu',
  functional_solution: 'Solution fonctionnelle proposée',
  technical_architecture: 'Architecture technique cible',
  integrations_and_interfaces: 'Intégrations et interfaces',
  security_compliance_governance: 'Sécurité, conformité et gouvernance des données',
  methodology_phases_deliverables: 'Démarche, phases et livrables',
  planning_and_milestones: 'Planning et jalons',
  team_and_governance: 'Équipe, rôles et gouvernance',
  testing_and_acceptance: 'Stratégie de tests et recette',
  migration_deployment_reversibility: 'Migration, déploiement et réversibilité',
  change_management_training: 'Conduite du changement, formation et transfert',
  operations_and_support: 'Exploitation, support et maintenance',
  risks_assumptions_clarifications: 'Risques, dépendances, hypothèses et points à clarifier',
  references_differentiation_next_steps: 'Références, différenciation Avaliance et prochaines étapes',
}

const mock19Sections = canonical19Keys.map((key, idx) => ({
  key,
  order: idx + 1,
  title: canonical19Titles[key],
  status: 'complete',
  narrative: [`Section ${idx + 1} narrative text for ${canonical19Titles[key]}.`],
  claims: [
    { id: `claim-${idx + 1}-1`, text: `Fait extrait du brief pour ${key}`, kind: 'brief_fact', sourceIds: ['brief'], citationIndexes: [] },
    { id: `claim-${idx + 1}-2`, text: `Recommandation méthodologique pour ${key}`, kind: 'recommendation', sourceIds: [], citationIndexes: [] },
    ...(key === 'references_differentiation_next_steps'
      ? [{
        id: 'claim-019-ref',
        text: 'Retour d\'expérience Santélia Santé (Page 1) : Déploiement d\'un portail patient sécurisé.',
        kind: 'internal_evidence',
        sourceIds: ['doc-01'],
        citationIndexes: [1],
      }]
      : []),
  ],
  bullets: key === 'scope_inclusions' ? ['Chantier 1 : Portail HDS', 'Chantier 2 : Connecteurs FHIR'] : [],
  tables: key === 'planning_and_milestones'
    ? [{ title: 'Jalons directeurs', columns: ['Jalon', 'Délai'], rows: [['Cadrage', 'T0 + 2 sem']] }]
    : [],
  questions: key === 'risks_assumptions_clarifications' ? ['Confirmer le calendrier des comités.'] : [],
  factsFromBrief: [`Fait extrait du brief pour ${key}`],
  verifiedReferences: key === 'references_differentiation_next_steps'
    ? [{
      id: 'claim-019-ref',
      text: 'Retour d\'expérience Santélia Santé (Page 1) : Déploiement d\'un portail patient sécurisé.',
      kind: 'internal_evidence',
      sourceIds: ['doc-01'],
      citationIndexes: [1],
    }]
    : [],
  recommendations: [`Recommandation méthodologique pour ${key}`],
  assumptionsToConfirm: [],
}))

test('[MOCKED-API] RFP proposal renders the six-section proposal, claim badges, citations, and actions', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const pageErrors: Error[] = []
  page.on('pageerror', (error) => pageErrors.push(error))

  // 1. Mock authentic P0 RFP API response with all 19 canonical sections
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
          sections: mock19Sections,
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
  await expect(page.getByText('Sections : 6/6')).toBeVisible()
  await expect(page.getByText('Sections produites').first()).toBeVisible()
  await expect(page.getByText('Références PDF').first()).toBeVisible()
  await expect(page.getByText('Validation').first()).toBeVisible()
  await expect(page.getByText('Prêt à valider').first()).toBeVisible()
  await expect(page.getByText('PDF').first()).toBeVisible()

  // Verify the structured proposal body
  await expect(page.locator('.rfp-proposal-section').first()).toBeVisible()

  // Verify Action Buttons
  await expect(page.getByRole('button', { name: 'Copier' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Télécharger' })).toBeVisible()

  // Click Copy
  await page.getByRole('button', { name: 'Copier' }).click()
  await expect(page.getByRole('status')).toContainText('Proposition copiée.')

  expect(pageErrors).toEqual([])
})

test('[MOCKED-API] RFP proposal renders honest fallback and warning when no evidence is found', async ({ page }) => {
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
          sections: mock19Sections,
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
          warnings: ['Aucune preuve PDF interne pertinente n’a été trouvée dans le corpus documentaire.'],
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
  await expect(page.locator('.rfp-no-evidence')).toContainText('Aucune preuve PDF interne pertinente n’a été trouvée dans la base interne')
  await expect(page.getByText('À compléter').first()).toBeVisible()
  await expect(page.getByText('Références PDF').first()).toBeVisible()

  expect(pageErrors).toEqual([])
})

test('[REAL-STACK] Live end-to-end RFP generation against backend without mocking', async ({ page }) => {
  test.skip(process.env.E2E_REAL_STACK !== 'true', 'Skipping live real-stack test (E2E_REAL_STACK not set)')
  test.setTimeout(450_000)

  const pageErrors: Error[] = []
  page.on('pageerror', (error) => pageErrors.push(error))

  // 1. Login
  await page.goto('/login')
  await page.getByLabel('Identifiant').fill(username)
  await page.locator('input[type="password"]').fill(password)
  await page.getByRole('button', { name: 'Se connecter' }).click()
  await expect(page).toHaveURL(/\/tableau-de-bord$/)

  // 2. Navigate to /propositions and run live generation
  await page.goto('/propositions')
  await page.getByLabel('Brief client ou cahier des charges').fill(brief)
  await page.getByRole('button', { name: 'Générer la proposition' }).click()

  // 3. Wait for real generation to complete (up to 420s)
  await expect(page.locator('.rfp-document')).toBeVisible({ timeout: 420_000 })
  await expect(page.getByText(/Sections : 6\/6/)).toBeVisible()
  await expect(page.getByText(/Validation|Prêt à valider|À compléter/).first()).toBeVisible()

  expect(pageErrors).toEqual([])
})
