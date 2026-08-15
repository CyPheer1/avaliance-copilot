import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { RfpProposal, RfpSection } from '../types.ts'

export function RfpProposalDocument({ proposal }: { proposal: RfpProposal }) {
  if (proposal.legacyMarkdown) {
    return <div className="markdown-document"><ReactMarkdown remarkPlugins={[remarkGfm]}>{proposal.legacyMarkdown}</ReactMarkdown></div>
  }

  return <div className="rfp-structured-document">{proposal.sections.map((section) => <StructuredSection key={section.key} section={section} />)}</div>
}

function StructuredSection({ section }: { section: RfpSection }) {
  // Brief facts guide composition but are not copied into the customer document.
  const prose = section.recommendations
  return <section className="rfp-proposal-section">
    <h3>{section.title}</h3>
    {prose.length > 0 && <div className="rfp-proposal-prose">{prose.map((item) => <p key={item}>{item}</p>)}</div>}
    {section.verifiedReferences.length > 0 && <div className="rfp-statement--evidence"><strong>Référence interne vérifiée</strong><ul>{section.verifiedReferences.map((item) => <li key={item.text}>{item.text} {item.citationIndexes.map((citationIndex) => <span className="citation-chip" key={citationIndex}>[{citationIndex}]</span>)}</li>)}</ul></div>}
    {section.tables.map((table) => <div className="rfp-table-wrap" key={table.title}><h4>{table.title}</h4><table><thead><tr>{table.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{table.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div>)}
    {section.assumptionsToConfirm.length > 0 && <div className="rfp-clarifications"><h4>Points à clarifier</h4><ul>{section.assumptionsToConfirm.map((item) => <li key={item}>{item}</li>)}</ul></div>}
  </section>
}
