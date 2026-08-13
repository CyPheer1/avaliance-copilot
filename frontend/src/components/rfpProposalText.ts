import type { RfpProposal } from '../types.ts'

export function proposalToText(proposal: RfpProposal): string {
  if (proposal.legacyMarkdown) return proposal.legacyMarkdown
  return [
    proposal.title,
    ...proposal.sections.flatMap((section) => [
      section.title,
      ...section.factsFromBrief,
      ...section.verifiedReferences.map((reference) => `${reference.text} ${reference.citationIndexes.map((index) => `[${index}]`).join(' ')}`),
      ...section.recommendations,
      ...section.assumptionsToConfirm,
      ...section.tables.flatMap((table) => [table.title, table.columns.join(' | '), ...table.rows.map((row) => row.join(' | '))]),
    ]),
  ].join('\n\n')
}
