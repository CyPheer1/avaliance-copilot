/**
 * Answer parsing and structured data extraction utilities.
 *
 * These pure functions parse the raw LLM answer text into structured data
 * for rendering as tables, fact cards, and summary groups. They were extracted
 * from SearchPage.tsx to keep the page component focused on layout and state.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type AnswerMode =
  | 'identity'
  | 'team'
  | 'budget'
  | 'scope'
  | 'objectives'
  | 'summary'
  | 'metrics'
  | 'architecture'
  | 'default'

export type MetricRow = {
  indicator: string
  before: string
  after: string
  evolution: string
  target: string
}

export type ArchitectureRow = {
  layer: string
  components: string
  justification: string
  citation: string
}

export type BudgetRow = {
  label: string
  amount: string
  share: string
}

// ---------------------------------------------------------------------------
// Text normalization
// ---------------------------------------------------------------------------

export function foldAnswerText(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
}

export function decodeAnswerEntities(value: string): string {
  return value
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
}

// ---------------------------------------------------------------------------
// Answer mode detection
// ---------------------------------------------------------------------------

export function detectAnswerMode(query: string): AnswerMode {
  const folded = foldAnswerText(query)
  if (folded.includes('fiche') && (folded.includes('identite') || folded.includes('complete')))
    return 'identity'
  if (
    folded.includes('equipe') &&
    (folded.includes('quelle') || folded.includes('composition') || folded.includes('projet'))
  )
    return 'team'
  if (folded.includes('budget')) return 'budget'
  if (
    folded.includes('perimetre') &&
    (folded.includes('exclu') || folded.includes('hors') || folded.includes('non inclus'))
  )
    return 'scope'
  if (folded.includes('objectif') && folded.includes('technique')) return 'objectives'
  if (
    folded.includes('resultat mesure') ||
    folded.includes('resultats mesures') ||
    folded.includes('indicateur')
  )
    return 'metrics'
  if (
    folded.includes('probleme initial') &&
    folded.includes('solution') &&
    (folded.includes('resultat') || folded.includes('impact'))
  )
    return 'summary'
  if (
    folded.includes('architecture') ||
    folded.includes('choix technique') ||
    folded.includes('mesures de securite') ||
    folded.includes('technologie')
  )
    return 'architecture'
  return 'default'
}

// ---------------------------------------------------------------------------
// Block splitting
// ---------------------------------------------------------------------------

export function splitAnswerBlocks(value: string): string[] {
  const cleaned = decodeAnswerEntities(value)
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\s+(?=##\s)/g, '\n\n')
    .replace(/;\s+-\s+(?=[A-ZÀ-ÖØ-Þ0-9])/g, ';\n- ')
  return cleaned
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean)
}

export function cleanAnswerBlock(value: string): string {
  return decodeAnswerEntities(value)
    .replace(/^#{1,6}\s+[^\n]+(?:\n|$)/, '')
    .replace(/^(?:CLIENT|SECTEUR):\s*[^\n]+(?:\n|$)/i, '')
    .trim()
}

// ---------------------------------------------------------------------------
// Structured data extraction
// ---------------------------------------------------------------------------

export function identityValues(_query: string, answer: string): string[] {
  const segments = answer
    .replace(/\s+\[(\d+)\]/g, ' [$1]\n')
    .split(/\n+/)
    .map((value) => value.trim())
    .filter(Boolean)
  return segments
    .slice(0, 6)
    .map((segment) => {
      const value = segment
        .replace(
          /^(?:CLIENT|SECTEUR):\s*(?:TYPE DE MISSION|PÉRIODE|BUDGET CONSOMMÉ|ÉQUIPE|RÉFÉRENCE|STATUT)\s*;\s*[^:;]+:\s*/i,
          '',
        )
        .replace(
          /^(?:CLIENT|SECTEUR|TYPE DE MISSION|PÉRIODE|BUDGET CONSOMMÉ|ÉQUIPE|RÉFÉRENCE|STATUT)\s*:\s*/i,
          '',
        )
        .replace(/^[^:;]{2,80}:\s*/, '')
        .trim()
      return value
    })
    .filter(Boolean)
}

export function metricRows(answer: string): MetricRow[] {
  const rows: MetricRow[] = []
  const pattern =
    /Indicateur:\s*(.*?);\s*Avant:\s*(.*?);\s*Après:\s*(.*?);\s*Évolution:\s*(.*?);\s*Cible:\s*(.*?)(?=\s+Indicateur:|$)/gi
  for (const match of answer.matchAll(pattern)) {
    rows.push({
      indicator: match[1].trim(),
      before: match[2].trim(),
      after: match[3].trim(),
      evolution: match[4].trim(),
      target: match[5].trim(),
    })
  }
  return rows
}

export function objectiveRows(answer: string): Array<{ text: string; citation: string }> {
  const rows: Array<{ text: string; citation: string }> = []
  const pattern = /^\s*-\s+(.+?)\s+\[(\d+)\]\s*$/gm
  for (const match of answer.matchAll(pattern))
    rows.push({ text: match[1].trim(), citation: `[${match[2]}]` })
  return rows
}

export function architectureRows(blocks: string[]): ArchitectureRow[] {
  const rows: ArchitectureRow[] = []
  const pattern =
    /Couche:\s*(.*?);\s*Composants retenus:\s*(.*?);\s*Justification:\s*(.*?)(?=\s+Couche:|\s+##|$)/gi
  for (const block of blocks) {
    const citation = block.match(/\[(\d+)\]\s*$/)?.[0] ?? ''
    for (const match of block.matchAll(pattern)) {
      rows.push({
        layer: match[1].trim(),
        components: match[2].trim(),
        justification: match[3].trim(),
        citation,
      })
    }
  }
  return rows
}

export function summaryGroups(
  blocks: string[],
): Array<{ label: string; blocks: string[] }> {
  const groups: Array<{ label: string; blocks: string[] }> = [
    { label: 'Contexte et problème initial', blocks: [] },
    { label: 'Solution retenue', blocks: [] },
    { label: 'Résultats établis', blocks: [] },
  ]
  for (const block of blocks) {
    const folded = foldAnswerText(block)
    if (
      /(a la cloture|six mois|atteint|diminu|recul|resultat|adoption|disponibilite)/.test(folded)
    )
      groups[2].blocks.push(block)
    else if (/(solution|cible|plateforme|feder|fhir|wms cloud|moteur)/.test(folded))
      groups[1].blocks.push(block)
    else groups[0].blocks.push(block)
  }
  return groups.filter((group) => group.blocks.length > 0)
}

export function budgetRows(answer: string): BudgetRow[] {
  const rows: BudgetRow[] = []
  const pattern = /Rubrique:\s*(.*?);\s*Montant HT:\s*(.*?);\s*Part:\s*([^\s]+%)/gi
  for (const match of answer.matchAll(pattern))
    rows.push({ label: match[1].trim(), amount: match[2].trim(), share: match[3].trim() })
  return rows
}

// ---------------------------------------------------------------------------
// Citation utilities
// ---------------------------------------------------------------------------

export function citationSourceIndexes(value: string): number[] {
  return Array.from(value.matchAll(/\[(\d+)\]/g), (match) => Number(match[1]))
}

export function sanitizeGeneratedAnswer(
  value: string,
  sourceIndexMap = new Map<number, number>(),
): string {
  const hasVerifiedSources = sourceIndexMap.size > 0
  return value
    .replace(/\s*\[(?:n|\d+)\]\s*Document\s*:[^\n]*(?:\n|$)/gi, '\n')
    .replace(/\[(\d+)\]/g, (_match, sourceIndex: string) => {
      const mapped = sourceIndexMap.get(Number(sourceIndex))
      if (mapped) return `[${mapped}]`
      return hasVerifiedSources ? `[${sourceIndex}]` : ''
    })
    .replace(/\[n\]/gi, hasVerifiedSources ? '[n]' : '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

import type { Citation } from '../../types.ts'

export function mergeCitations(incoming: Citation[], existing: Citation[] = []): Citation[] {
  const citationsBySource = new Map<string, Citation>()
  for (const citation of [...existing, ...incoming]) {
    const key = citation.citationId ?? `${citation.chunkId}-${citation.sourceIndex ?? ''}`
    citationsBySource.set(key, citation)
  }
  return Array.from(citationsBySource.values())
}

export function sourceCardIndexBySourceIndex(citations: Citation[]): Map<number, number> {
  return new Map(
    citations.map((citation, cardIndex) => [citation.sourceIndex ?? cardIndex + 1, cardIndex]),
  )
}
