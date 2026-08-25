/**
 * Presentational sub-components for the search results workspace.
 *
 * Extracted from SearchPage.tsx to keep the page component focused on
 * orchestration (streaming, state) rather than render details.
 */

import type { ReactNode } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BookOpenCheck,
  Download,
  ExternalLink,
  Maximize2,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router-dom'
import type { Citation } from '../../types.ts'
import {
  architectureRows,
  budgetRows,
  cleanAnswerBlock,
  decodeAnswerEntities,
  detectAnswerMode,
  identityValues,
  metricRows,
  objectiveRows,
  sourceCardIndexBySourceIndex,
  splitAnswerBlocks,
  summaryGroups,
} from './answer-parsing.ts'

// ---------------------------------------------------------------------------
// Citation rendering helpers
// ---------------------------------------------------------------------------

function renderCitationNodes(
  children: ReactNode,
  sourceCards: Map<number, number>,
  onSelect: (index: number) => void,
): ReactNode {
  if (typeof children === 'string') {
    const parts = decodeAnswerEntities(children).split(/(\[(?:\d+|n)\])/gi)
    return parts.map((part, index) => {
      const match = part.match(/^\[(\d+|n)\]$/i)
      if (!match) return part
      const citationNumber = match[1].toLowerCase() === 'n' ? 1 : Number(match[1])
      const cardIndex = sourceCards.get(citationNumber)
      if (cardIndex == null) return part
      return (
        <button
          className="citation-chip"
          type="button"
          key={`${citationNumber}-${index}`}
          onClick={() => onSelect(cardIndex)}
          aria-label={`Ouvrir la source ${citationNumber}`}
        >
          [{citationNumber}]
        </button>
      )
    })
  }
  if (Array.isArray(children))
    return children.map((child, index) => (
      <span key={index}>{renderCitationNodes(child, sourceCards, onSelect)}</span>
    ))
  return children
}

// ---------------------------------------------------------------------------
// MarkdownAnswer — fallback renderer when no structured mode matches
// ---------------------------------------------------------------------------

function MarkdownAnswer({
  answer,
  sourceCards,
  onSelect,
}: {
  answer: string
  sourceCards: Map<number, number>
  onSelect: (index: number) => void
}) {
  return (
    <ReactMarkdown
      components={{
        p: ({ children }) => <p>{renderCitationNodes(children, sourceCards, onSelect)}</p>,
        li: ({ children }) => <li>{renderCitationNodes(children, sourceCards, onSelect)}</li>,
        h1: ({ children }) => <h3>{children}</h3>,
        h2: ({ children }) => <h3>{children}</h3>,
        h3: ({ children }) => <h4>{children}</h4>,
      }}
    >
      {decodeAnswerEntities(answer)}
    </ReactMarkdown>
  )
}

// ---------------------------------------------------------------------------
// StructuredAnswer — dispatches to mode-specific layouts
// ---------------------------------------------------------------------------

export function StructuredAnswer({
  query,
  answer,
  citations,
  onSelect,
}: {
  query: string
  answer: string
  citations: Citation[]
  onSelect: (index: number) => void
}) {
  const sourceCards = sourceCardIndexBySourceIndex(citations)
  const blocks = splitAnswerBlocks(answer)
  const mode = detectAnswerMode(query)
  const renderEvidence = (value: string, index: number, className = '') => (
    <p className={className} key={`${index}-${value.slice(0, 24)}`}>
      {renderCitationNodes(cleanAnswerBlock(value), sourceCards, onSelect)}
    </p>
  )

  if (mode === 'identity') {
    const values = identityValues(query, answer)
    const labels = ['Mission', 'Période', 'Budget consommé', 'Équipe', 'Référence', 'Statut']
    if (values.length >= 4) {
      const projectContext = query.match(/projet\s+(.+?)(?:|\s+—)/i)?.[1]?.trim()
      return (
        <div className="answer-structured answer-structured--identity">
          {projectContext && (
            <div className="answer-context-line">
              <span>Projet demandé</span>
              <strong>{projectContext}</strong>
            </div>
          )}
          <div className="answer-fact-grid">
            {values.map((value, index) => (
              <div
                className="answer-fact-card"
                key={`${labels[index] ?? 'fait'}-${index}`}
              >
                <span className="answer-fact-card__label">
                  {labels[index] ?? 'Fait établi'}
                </span>
                <div>{renderCitationNodes(value, sourceCards, onSelect)}</div>
              </div>
            ))}
          </div>
        </div>
      )
    }
  }

  if (mode === 'team') {
    const match = answer.match(/(\d+\s+personnes\s*\([^)]*\))/i)
    const value = match?.[1] ?? cleanAnswerBlock(answer)
    return (
      <div className="answer-structured answer-structured--field">
        <div className="answer-structured__eyebrow">Équipe mobilisée</div>
        <section className="answer-fact-card answer-fact-card--wide">
          <span className="answer-fact-card__label">Composition de l'équipe</span>
          <div>
            Le projet a mobilisé{' '}
            {renderCitationNodes(`${value} [1]`, sourceCards, onSelect)}
          </div>
        </section>
      </div>
    )
  }

  if (mode === 'budget') {
    const rows = budgetRows(answer)
    if (rows.length > 0)
      return (
        <div className="answer-structured answer-structured--budget">
          <div className="answer-structured__eyebrow">Répartition budgétaire</div>
          <div className="answer-table-wrap">
            <table className="answer-facts-table">
              <thead>
                <tr>
                  <th>Rubrique</th>
                  <th>Montant HT</th>
                  <th>Part</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`${row.label}-${index}`}>
                    <td>{row.label}</td>
                    <td>
                      {renderCitationNodes(`${row.amount} [1]`, sourceCards, onSelect)}
                    </td>
                    <td>
                      {renderCitationNodes(`${row.share} [1]`, sourceCards, onSelect)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )
  }

  if (mode === 'scope') {
    return (
      <div className="answer-structured answer-structured--scope">
        <div className="answer-structured__eyebrow">Périmètre exclu</div>
        <section className="answer-summary-card">
          <h3>Ce qui n'était pas inclus</h3>
          {blocks.map((block, index) => renderEvidence(block, index))}
        </section>
      </div>
    )
  }

  if (mode === 'objectives') {
    const rows = objectiveRows(answer)
    if (rows.length > 0)
      return (
        <div className="answer-structured answer-structured--objectives">
          <div className="answer-structured__eyebrow">Objectifs techniques</div>
          <section className="answer-summary-card">
            <h3>Ce que la cible devait garantir</h3>
            <ul>
              {rows.map((row, index) => (
                <li key={`${index}-${row.text.slice(0, 24)}`}>
                  {renderCitationNodes(
                    `${row.text} ${row.citation}`,
                    sourceCards,
                    onSelect,
                  )}
                </li>
              ))}
            </ul>
          </section>
        </div>
      )
  }

  if (mode === 'metrics') {
    const rows = metricRows(answer)
    if (rows.length > 0) {
      return (
        <div className="answer-structured answer-structured--metrics">
          <div className="answer-structured__eyebrow">Indicateurs retrouvés</div>
          <div className="answer-table-wrap">
            <table className="answer-facts-table">
              <thead>
                <tr>
                  <th>Indicateur</th>
                  <th>Avant</th>
                  <th>Après</th>
                  <th>Évolution</th>
                  <th>Cible</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`${row.indicator}-${index}`}>
                    <td>
                      {renderCitationNodes(row.indicator, sourceCards, onSelect)}
                    </td>
                    <td>{renderCitationNodes(row.before, sourceCards, onSelect)}</td>
                    <td>{renderCitationNodes(row.after, sourceCards, onSelect)}</td>
                    <td>
                      {renderCitationNodes(row.evolution, sourceCards, onSelect)}
                    </td>
                    <td>{renderCitationNodes(row.target, sourceCards, onSelect)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )
    }
  }

  if (mode === 'summary') {
    const groups = summaryGroups(blocks)
    if (groups.length >= 2)
      return (
        <div className="answer-structured answer-structured--summary">
          {groups.map((group) => (
            <section className="answer-summary-card" key={group.label}>
              <h3>{group.label}</h3>
              {group.blocks.map((block, index) => renderEvidence(block, index))}
            </section>
          ))}
        </div>
      )
  }

  if (mode === 'architecture') {
    const rows = architectureRows(blocks)
    const securityBlocks = blocks.filter(
      (block) =>
        !/Couche:/i.test(block) &&
        /(sécurité|mfa|chiffrement|certificat|journal|contrôle d'accès|accès par rôle|conformité)/i.test(
          block,
        ),
    )
    if (rows.length > 0)
      return (
        <div className="answer-structured answer-structured--architecture">
          <div className="answer-structured__eyebrow">Architecture retenue</div>
          <div className="answer-table-wrap">
            <table className="answer-facts-table answer-architecture-table">
              <thead>
                <tr>
                  <th>Couche</th>
                  <th>Composants retenus</th>
                  <th>Justification</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`${row.layer}-${index}`}>
                    <td>{row.layer}</td>
                    <td>
                      {renderCitationNodes(
                        `${row.components} ${row.citation}`,
                        sourceCards,
                        onSelect,
                      )}
                    </td>
                    <td>
                      {renderCitationNodes(
                        `${row.justification} ${row.citation}`,
                        sourceCards,
                        onSelect,
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {securityBlocks.length > 0 && (
            <section className="answer-security-card">
              <h3>Sécurité et conformité</h3>
              {securityBlocks.map((block, index) =>
                renderEvidence(block, index, 'answer-security-card__text'),
              )}
            </section>
          )}
        </div>
      )
    return (
      <div className="answer-structured answer-structured--architecture">
        <div className="answer-structured__eyebrow">Éléments techniques retrouvés</div>
        {blocks.map((block, index) => (
          <div
            className="answer-evidence-block"
            key={`${index}-${block.slice(0, 24)}`}
          >
            {renderEvidence(block, index)}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="answer-structured answer-structured--default">
      <MarkdownAnswer answer={answer} sourceCards={sourceCards} onSelect={onSelect} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// SourceCard
// ---------------------------------------------------------------------------

export function SourceCard({
  citation,
  index,
  selected,
  onSelect,
}: {
  citation: Citation
  index: number
  selected: boolean
  onSelect: () => void
}) {
  const title = citation.documentName ?? citation.missionTitle ?? `Source ${citation.chunkId}`
  return (
    <article className={`source-card ${selected ? 'source-card--selected' : ''}`}>
      <div className="source-card__top">
        <button
          className="source-card__number"
          type="button"
          onClick={onSelect}
          aria-label={`Sélectionner la source ${index + 1}`}
        >
          [{index + 1}]
        </button>
        <span className="source-card__label">Preuve retrouvée</span>
      </div>
      <h3 title={title}>{title}</h3>
      <div className="source-card__meta">
        <span>
          {citation.page != null ? `Page physique ${citation.page}` : 'Page non précisée'}
        </span>
        <span>Chunk {citation.chunkId}</span>
        {citation.missionTitle && <span>{citation.missionTitle}</span>}
      </div>
      <blockquote>{citation.content}</blockquote>
      <div className="source-card__actions">
        <button className="link-button" type="button" onClick={onSelect}>
          Voir dans le document <ArrowUpRight size={15} />
        </button>
        {citation.missionId !== null && (
          <Link to={`/missions/${citation.missionId}`}>
            Ouvrir la mission <ExternalLink size={14} />
          </Link>
        )}
      </div>
    </article>
  )
}

// ---------------------------------------------------------------------------
// DocumentViewer
// ---------------------------------------------------------------------------

export function DocumentViewer({
  pdfPreview,
  pdfPage,
  pdfZoom,
  pdfLoading,
  pdfFailed,
  canDownloadPdf,
  documentSrc,
  frameRef,
  onClose,
  onPageChange,
  onZoomChange,
  onFullscreen,
}: {
  pdfPreview: { citation: Citation; url: string } | null
  pdfPage: number
  pdfZoom: number
  pdfLoading: boolean
  pdfFailed: boolean
  canDownloadPdf: boolean
  documentSrc: string
  frameRef: { current: HTMLIFrameElement | null }
  onClose: () => void
  onPageChange: (page: number) => void
  onZoomChange: (zoom: number) => void
  onFullscreen: () => void
}) {
  if (!pdfPreview)
    return (
      <div className="document-empty" role="tabpanel">
        <div className="document-empty__icon">
          <BookOpenCheck size={24} />
        </div>
        <h3>Choisissez une source</h3>
        <p>La page citée et son extrait apparaîtront ici pour vérification.</p>
      </div>
    )
  const filename = pdfPreview.citation.documentName ?? 'document-source.pdf'
  return (
    <div className="document-viewer" role="tabpanel">
      <header className="document-viewer__header">
        <div>
          <span className="eyebrow">Document source</span>
          <h3 title={filename}>{filename}</h3>
          <span>Page physique {pdfPage}</span>
        </div>
        <button
          className="icon-button"
          type="button"
          onClick={onClose}
          aria-label="Fermer le document"
          title="Fermer"
        >
          <X size={17} />
        </button>
      </header>
      <div className="document-viewer__toolbar">
        <div className="viewer-controls">
          <button
            className="icon-button"
            type="button"
            disabled={pdfPage <= 1}
            onClick={() => onPageChange(Math.max(1, pdfPage - 1))}
            aria-label="Page précédente"
            title="Page précédente"
          >
            <ArrowLeft size={16} />
          </button>
          <span>Page {pdfPage}</span>
          <button
            className="icon-button"
            type="button"
            onClick={() => onPageChange(pdfPage + 1)}
            aria-label="Page suivante"
            title="Page suivante"
          >
            <ArrowRight size={16} />
          </button>
        </div>
        <div className="viewer-controls">
          <button
            className="icon-button"
            type="button"
            disabled={pdfZoom <= 75}
            onClick={() => onZoomChange(Math.max(75, pdfZoom - 25))}
            aria-label="Réduire le zoom"
            title="Réduire le zoom"
          >
            <ZoomOut size={16} />
          </button>
          <span>{pdfZoom}%</span>
          <button
            className="icon-button"
            type="button"
            disabled={pdfZoom >= 150}
            onClick={() => onZoomChange(Math.min(150, pdfZoom + 25))}
            aria-label="Augmenter le zoom"
            title="Augmenter le zoom"
          >
            <ZoomIn size={16} />
          </button>
          <button
            className="icon-button"
            type="button"
            onClick={onFullscreen}
            aria-label="Afficher en plein écran"
            title="Plein écran"
          >
            <Maximize2 size={16} />
          </button>
        </div>
      </div>
      {pdfLoading && (
        <div className="document-viewer__state">
          <span className="stream-status__dot stream-status__dot--pulse" /> Chargement du
          document…
        </div>
      )}
      {pdfFailed && (
        <div className="document-viewer__state document-viewer__state--error">
          <AlertTriangle size={18} /> Impossible de charger ce document.
        </div>
      )}
      <iframe
        ref={(node) => {
          frameRef.current = node
        }}
        className="document-viewer__frame"
        title={filename}
        src={documentSrc}
        onError={() => undefined}
      />
      {canDownloadPdf && (
        <a className="document-viewer__download" href={pdfPreview.url} download={filename}>
          <Download size={15} /> Télécharger le PDF
        </a>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// EmptySearch — landing state
// ---------------------------------------------------------------------------

export function EmptySearch() {
  return (
    <section className="empty-brief">
      <BookOpenCheck size={24} />
      <span className="eyebrow">Mode d'emploi</span>
      <h2>Une réponse n'a de valeur que si elle reste vérifiable.</h2>
      <p>
        Décrivez le contexte, le secteur ou la technologie recherchée. Les citations permettent
        d'ouvrir directement les missions de référence.
      </p>
      <div>
        <span>01</span>
        <p>Recherche vectorielle et textuelle en parallèle</p>
        <span>02</span>
        <p>Réponse strictement limitée aux preuves retrouvées</p>
      </div>
    </section>
  )
}
