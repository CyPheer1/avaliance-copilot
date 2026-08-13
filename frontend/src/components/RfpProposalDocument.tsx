import type { RfpEvidence, RfpProposal, RfpSection } from '../types.ts'

export function RfpProposalDocument({ proposal, evidence }: { proposal: RfpProposal; evidence: RfpEvidence[] }) {
  const evidenceById = new Map(evidence.map((item) => [item.id, item]))
  return <div className="rfp-structured-document">{proposal.sections.map((section) => <StructuredSection key={section.id} section={section} evidenceById={evidenceById} />)}</div>
}

function StructuredSection({ section, evidenceById }: { section: RfpSection; evidenceById: Map<string, RfpEvidence> }) {
  const Heading = section.level === 1 ? 'h2' : 'h3'
  return <section className="rfp-proposal-section">
    <Heading>{section.title}</Heading>
    {section.blocks.map((block, blockIndex) => <div className={`rfp-block rfp-block--${block.kind}`} key={`${section.id}-${blockIndex}`}>
      {block.kind === 'paragraph' && block.text && <p>{block.text}</p>}
      {block.kind === 'callout' && block.text && <p>{block.text}</p>}
      {block.kind === 'bullets' && block.items.length > 0 && <ul>{block.items.map((item) => <li key={item}>{item}</li>)}</ul>}
      {block.kind === 'table' && block.table && <div className="rfp-table-wrap"><h4>{block.table.title}</h4><table><thead><tr>{block.table.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{block.table.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table></div>}
      {block.evidenceIds.length > 0 && <span className="rfp-inline-citations">{block.evidenceIds.map((id) => {
        const item = evidenceById.get(id)
        return item ? <a key={id} href={`#${id}`} title={item.quote}>[p. {item.page}]</a> : null
      })}</span>}
    </div>)}
  </section>
}
