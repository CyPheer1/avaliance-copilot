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

    const bodyText = section.body || section.summary
    if (bodyText) {
      lines.push(bodyText)
    }
    
    if (section.evidence && section.evidence.length > 0) {
      lines.push('Références internes vérifiées : ' + section.evidence.map((ev) => `[${ev.id}]`).join(' '))
    }

    const bullets = section.bullets?.slice(0, 3) || []
    if (bullets.length > 0) {
      lines.push(...bullets.map((b) => `- ${b.text}`))
    }

    if (section.tables && section.tables.length > 0) {
      for (const table of section.tables) {
        lines.push(
          table.title,
          table.columns.join(' | '),
          table.columns.map(() => '---').join(' | '),
          ...table.rows.map((row) => row.join(' | '))
        )
      }
    }
    
    const assumptions = (section.assumptions || section.assumptionsToConfirm || []).slice(0, 2)
    if (assumptions.length > 0) {
      lines.push('Hypothèses et points à confirmer :', ...assumptions.map((a) => `- ${a}`))
    }

    const questions = (section.questions || []).slice(0, 3)
    if (questions.length > 0) {
      lines.push('Questions de cadrage :', ...questions.map((q) => `? ${q}`))
    }
  }

  return lines.join('\n\n')
}
