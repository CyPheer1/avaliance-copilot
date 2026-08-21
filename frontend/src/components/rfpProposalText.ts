import type { RfpProposal } from '../types.ts'

export function proposalToText(proposal: RfpProposal): string {
  const lines: string[] = [proposal.title]

  if (proposal.executiveSummary) {
    lines.push('SYNTHÈSE EXÉCUTIVE', proposal.executiveSummary)
  }

  for (const section of proposal.sections) {
    lines.push(`## ${section.order ? `${section.order}. ` : ''}${section.title}`)

    if (section.status === 'not_applicable') {
      lines.push(`[Section non applicable : ${section.statusReason || 'Non requis pour ce périmètre'}]`)
      continue
    }

    if (section.summary) {
      lines.push(section.summary)
    }
    if (section.body) {
      lines.push(section.body)
    }

    if (section.narrative && section.narrative.length > 0) {
      lines.push(...section.narrative)
    }

    if (section.factsFromBrief.length > 0) {
      lines.push('Éléments du brief :', ...section.factsFromBrief.map((f) => `- ${f}`))
    }

    if (section.bullets && section.bullets.length > 0) {
      lines.push(...section.bullets.map((b) => `- ${b.text}${b.anchor?.id ? ` [${b.anchor.id}]` : ''}`))
    }

    if (section.verifiedReferences.length > 0) {
      lines.push(
        'Références internes vérifiées :',
        ...section.verifiedReferences.map(
          (ref) => `- ${ref.text} ${ref.citationIndexes.map((idx) => `[${idx}]`).join(' ')}`
        )
      )
    }

    if (section.recommendations.length > 0 && (!section.narrative || section.narrative.length === 0)) {
      lines.push(...section.recommendations)
    }

    if (section.tables.length > 0) {
      for (const table of section.tables) {
        lines.push(
          table.title,
          table.columns.join(' | '),
          table.columns.map(() => '---').join(' | '),
          ...table.rows.map((row) => row.join(' | '))
        )
      }
    }

    if (section.assumptionsToConfirm.length > 0) {
      lines.push('Hypothèses et points à confirmer :', ...section.assumptionsToConfirm.map((a) => `- ${a}`))
    }

    if (section.questions && section.questions.length > 0) {
      lines.push('Questions de cadrage :', ...section.questions.map((q) => `? ${q}`))
    }
  }

  return lines.join('\n\n')
}
