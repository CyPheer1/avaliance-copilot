import type { RfpProposal, RfpSection } from '../types.ts'

function ExecutiveSummary({ text }: { text: string }) {
  const marker = 'Exigence couverte :'
  const parts = text.split(marker)
  const intro = parts.shift()?.trim() || text.trim()
  const requirements = parts.map((part) => part.trim()).filter(Boolean)

  return (
    <div className="rfp-executive-banner">
      <div className="rfp-executive-banner__topline">
        <span className="rfp-executive-badge">Synthèse exécutive</span>
        <span className="rfp-executive-banner__label">Lecture rapide du besoin</span>
      </div>
      <p className="rfp-executive-text">{intro}</p>
      {requirements.length > 0 && (
        <div className="rfp-executive-requirements">
          <div className="rfp-executive-requirements__title">Exigences clés</div>
          <ul>
            {requirements.map((requirement, index) => <li key={index}>{requirement}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}

export function RfpProposalDocument({ proposal }: { proposal: RfpProposal }) {
  return (
    <div className="rfp-structured-document">
      {proposal.executiveSummary && <ExecutiveSummary text={proposal.executiveSummary} />}
      {proposal.sections.slice(0, 6).map((section) => (
        <StructuredSection key={section.key} section={section} />
      ))}
    </div>
  )
}

function StructuredSection({ section }: { section: RfpSection }) {
  const isNotApplicable = section.status === 'not_applicable'
  const isRequiresClarification = section.status === 'requires_clarification'
  const bodyText = section.body || section.summary
  const bullets = section.bullets?.slice(0, 4) || []
  const assumptions = (section.assumptions || section.assumptionsToConfirm || []).slice(0, 2)
  const questions = (section.questions || []).slice(0, 3)

  return (
    <section className={`rfp-proposal-section ${isNotApplicable ? 'rfp-section--not-applicable' : ''}`}>
      <div className="rfp-section-header">
        <h3>
          {section.order ? <span className="rfp-section-order">{section.order}</span> : null}
          <span>{section.title}</span>
        </h3>
        <div className="rfp-section-status">
          {isNotApplicable && <span className="rfp-status-pill rfp-status-pill--muted">Non applicable</span>}
          {isRequiresClarification && <span className="rfp-status-pill rfp-status-pill--warning">À clarifier</span>}
        </div>
      </div>

      {isNotApplicable && section.statusReason && (
        <div className="rfp-status-reason"><em>{section.statusReason}</em></div>
      )}

      {!isNotApplicable && (
        <div className="rfp-section-content">
          {bodyText && <p className="rfp-section-summary">{bodyText}</p>}

          {section.evidence && section.evidence.length > 0 && (
            <div className="rfp-statement--evidence">
              <strong>Références internes vérifiées</strong>
              <div className="rfp-evidence-chips">
                {section.evidence.map((ev, idx) => (
                  <span className="citation-chip" key={idx} title={`Source PDF [${ev.id}]`}>[{ev.id}]</span>
                ))}
              </div>
            </div>
          )}

          {bullets.length > 0 && (
            <div className="rfp-detail-block rfp-detail-block--actions">
              <h4>Points de mise en œuvre</h4>
              <ul className="rfp-bullets-list">
                {bullets.map((bullet, idx) => <li key={idx}>{bullet.text}</li>)}
              </ul>
            </div>
          )}

          {section.tables && section.tables.map((table, tIdx) => (
            <div className="rfp-table-wrap" key={tIdx}>
              <h4>{table.title}</h4>
              <table>
                <thead><tr>{table.columns.map((column, cIdx) => <th key={cIdx}>{column}</th>)}</tr></thead>
                <tbody>{table.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody>
              </table>
            </div>
          ))}

          {assumptions.length > 0 && (
            <div className="rfp-clarifications">
              <h4>Hypothèses structurantes <span>À confirmer</span></h4>
              <ul>{assumptions.map((item, idx) => <li key={idx}>{item}</li>)}</ul>
            </div>
          )}

          {questions.length > 0 && (
            <div className="rfp-questions-block">
              <h4>Points de cadrage à clarifier</h4>
              <ul>{questions.map((q, idx) => <li key={idx}>{q}</li>)}</ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
