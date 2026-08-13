import type { RfpProposal } from '../types.ts'

export function proposalToText(proposal: RfpProposal): string {
  return [
    proposal.title,
    ...proposal.sections.flatMap((section) => [
      section.title,
      ...section.blocks.flatMap((block) => {
        if (block.kind === 'table' && block.table) return [block.table.title, block.table.columns.join(' | '), ...block.table.rows.map((row) => row.join(' | '))]
        if (block.kind === 'bullets') return block.items.map((item) => `• ${item}`)
        return block.text ? [block.text] : []
      }),
    ]),
  ].join('\n\n')
}
