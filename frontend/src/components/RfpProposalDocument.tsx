import type { RfpProposal, RfpSection } from '../types.ts'

export function RfpProposalDocument({ proposal }: { proposal: RfpProposal }) {
  return (
    <div className="rfp-structured-document">
      {proposal.executiveSummary && (
        <div className="rfp-executive-banner">
          <div className="rfp-executive-badge">Synthèse Exécutive</div>
          <p className="rfp-executive-text">{proposal.executiveSummary}</p>
        </div>
      )}
      {proposal.sections.map((section) => (
        <StructuredSection key={section.key} section={section} />
      ))}
    </div>
  )
}

function StructuredSection({ section }: { section: RfpSection }) {
  const isNotApplicable = section.status === 'not_applicable'
  const isRequiresClarification = section.status === 'requires_clarification'

  const narrativeParagraphs = section.narrative && section.narrative.length > 0 ? section.narrative : []
  const recommendations = section.recommendations && section.recommendations.length > 0 ? section.recommendations : []
  const prose = narrativeParagraphs.length > 0 ? narrativeParagraphs : recommendations

  return (
    <section className={`rfp-proposal-section ${isNotApplicable ? 'rfp-section--not-applicable' : ''}`}>
      <div className="rfp-section-header">
        <h3>
          {section.order ? <span className="rfp-section-order">{section.order}. </span> : null}
          {section.title}
        </h3>
        {isNotApplicable && (
          <span className="rfp-status-pill rfp-status-pill--muted">
            Non applicable
          </span>
        )}
        {isRequiresClarification && (
          <span className="rfp-status-pill rfp-status-pill--warning">
            À clarifier
          </span>
        )}
      </div>

      {isNotApplicable && section.statusReason && (
        <div className="rfp-status-reason">
          <em>{section.statusReason}</em>
        </div>
      )}

      {!isNotApplicable && (
        <>
          {section.summary && <p className="rfp-section-summary">{section.summary}</p>}
          {section.body && <p className="rfp-section-summary">{section.body}</p>}

          {prose.length > 0 && (
            <div className="rfp-proposal-prose">
              {prose.map((item, idx) => (
                <p key={idx}>{item}</p>
              ))}
            </div>
          )}

          {section.claims && section.claims.length > 0 && (
            <div className="rfp-claims-stream">
              {section.claims.some((c) => c.kind === 'brief_fact') && (
                <div className="rfp-claim-group rfp-claim-group--brief">
                  <strong>Faits issus du brief client</strong>
                  <ul>
                    {section.claims.filter((c) => c.kind === 'brief_fact').map((c, idx) => (
                      <li key={c.id || idx}>{c.text}</li>
                    ))}
                  </ul>
                </div>
              )}
              {section.claims.some((c) => c.kind === 'internal_evidence') && (
                <div className="rfp-claim-group rfp-claim-group--evidence">
                  <strong>Références internes vérifiées</strong>
                  <ul>
                    {section.claims.filter((c) => c.kind === 'internal_evidence').map((c, idx) => (
                      <li key={c.id || idx}>
                        {c.text}{' '}
                        {c.citationIndexes && c.citationIndexes.map((ci) => (
                          <span className="citation-chip" key={ci} title={`Source PDF [${ci}]`}>
                            [{ci}]
                          </span>
                        ))}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {section.claims.some((c) => c.kind === 'recommendation') && (
                <div className="rfp-claim-group rfp-claim-group--recommendation">
                  <strong>Recommandations méthodologiques & techniques</strong>
                  <ul>
                    {section.claims.filter((c) => c.kind === 'recommendation').map((c, idx) => (
                      <li key={c.id || idx}>{c.text}</li>
                    ))}
                  </ul>
                </div>
              )}
              {section.claims.some((c) => c.kind === 'assumption') && (
                <div className="rfp-claim-group rfp-claim-group--assumption">
                  <strong>Hypothèses structurantes (à confirmer)</strong>
                  <ul>
                    {section.claims.filter((c) => c.kind === 'assumption').map((c, idx) => (
                      <li key={c.id || idx}>{c.text}</li>
                    ))}
                  </ul>
                </div>
              )}
              {section.claims.some((c) => c.kind === 'question') && (
                <div className="rfp-claim-group rfp-claim-group--question">
                  <strong>Points de cadrage à clarifier</strong>
                  <ul>
                    {section.claims.filter((c) => c.kind === 'question').map((c, idx) => (
                      <li key={c.id || idx}>{c.text}</li>
                    ))}
                  </ul>
                </div>
              )}
              {section.claims.some((c) => c.kind === 'web_evidence') && (
                <div className="rfp-claim-group rfp-claim-group--web">
                  <strong>Sources externes</strong>
                  <ul>
                    {section.claims.filter((c) => c.kind === 'web_evidence').map((c, idx) => (
                      <li key={c.id || idx}>{c.text}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {(!section.claims || section.claims.length === 0) && section.verifiedReferences.length > 0 && (
            <div className="rfp-statement--evidence">
              <strong>Référence interne vérifiée</strong>
              <ul>
                {section.verifiedReferences.map((item, idx) => (
                  <li key={idx}>
                    {item.text}{' '}
                    {item.citationIndexes && item.citationIndexes.map((citationIndex) => (
                      <span className="citation-chip" key={citationIndex}>
                        [{citationIndex}]
                      </span>
                    ))}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {section.bullets && section.bullets.length > 0 && (
            <ul className="rfp-bullets-list">
              {section.bullets.map((bullet, idx) => (
                <li key={idx}>{bullet.text}</li>
              ))}
            </ul>
          )}

          {section.tables && section.tables.map((table, tIdx) => (
            <div className="rfp-table-wrap" key={tIdx}>
              <h4>{table.title}</h4>
              <table>
                <thead>
                  <tr>
                    {table.columns.map((column, cIdx) => (
                      <th key={cIdx}>{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {row.map((cell, cellIndex) => (
                        <td key={cellIndex}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          {section.assumptionsToConfirm && section.assumptionsToConfirm.length > 0 && (
            <div className="rfp-clarifications">
              <h4>Points à clarifier & Hypothèses</h4>
              <ul>
                {section.assumptionsToConfirm.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ul>
            </div>
          )}

          {section.questions && section.questions.length > 0 && (
            <div className="rfp-questions-block">
              <h4>Questions ouvertes de cadrage</h4>
              <ul>
                {section.questions.map((q, idx) => (
                  <li key={idx}>{q}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  )
}
