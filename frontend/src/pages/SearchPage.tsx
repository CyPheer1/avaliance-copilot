import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import type { ReactNode } from 'react'
import { AlertTriangle, ArrowLeft, ArrowRight, ArrowUp, ArrowUpRight, BookOpenCheck, Clipboard, Download, ExternalLink, FileText, Maximize2, MessageSquare, Quote, SlidersHorizontal, Square, X, ZoomIn, ZoomOut } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { Link } from 'react-router-dom'
import logoSrc from '../assets/logo.png'
import { api, errorMessage, searchStream } from '../api/client.ts'
import { ErrorState } from '../components/AsyncState.tsx'
import { PageHeader } from '../components/PageHeader.tsx'
import { useAuth } from '../auth/auth-context.ts'
import type { Citation } from '../types.ts'

const sectors = ['banque', 'assurance', 'télécom', 'transport', 'énergie']
const missionTypes = ['modernisation applicative', 'migration cloud', 'data/BI', 'cybersécurité', 'DevOps']

type StreamState = 'idle' | 'retrieving' | 'streaming' | 'done' | 'error'

export function SearchPage() {
  const { session } = useAuth()
  const [query, setQuery] = useState('')
  const [sector, setSector] = useState('')
  const [missionType, setMissionType] = useState('')
  const [year, setYear] = useState('')
  const [topK, setTopK] = useState(15)
  const [filtersOpen, setFiltersOpen] = useState(false)

  const [streamState, setStreamState] = useState<StreamState>('idle')
  const [answer, setAnswer] = useState('')
  const [citations, setCitations] = useState<Citation[]>([])
  const citationsRef = useRef<Citation[]>([])
  const validationPassedRef = useRef<boolean | null>(null)
  const [activeCitation, setActiveCitation] = useState<number | null>(null)
  const [evidenceTab, setEvidenceTab] = useState<'sources' | 'document'>('sources')
  const [pdfPreview, setPdfPreview] = useState<{ citation: Citation; url: string } | null>(null)
  const [pdfPage, setPdfPage] = useState(1)
  const [pdfZoom, setPdfZoom] = useState(100)
  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfFailed, setPdfFailed] = useState(false)
  const [copied, setCopied] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const [streamMetrics, setStreamMetrics] = useState<Record<string, number>>({})
  const pdfFrameRef = useRef<HTMLIFrameElement>(null)
  const streamControllerRef = useRef<AbortController | null>(null)
  const requestStartedAtRef = useRef<number | null>(null)
  const firstTokenRenderedRef = useRef(false)

  useEffect(() => {
    ;(window as typeof window & { __avalianceStreamMetrics?: Record<string, number> }).__avalianceStreamMetrics = streamMetrics
  }, [streamMetrics])

  // Ref to keep latest answer for streaming append
  const answerRef = useRef('')
  const answerEndRef = useRef<HTMLDivElement>(null)
  const renderFrameRef = useRef<number | null>(null)

  const openPdf = async (c: Citation) => {
    if (c.documentId == null) return
    const citationIndex = citations.findIndex((item) =>
      item.citationId != null && item.citationId === c.citationId
        ? true
        : item.chunkId === c.chunkId && item.sourceIndex === c.sourceIndex,
    )
    setActiveCitation(citationIndex >= 0 ? citationIndex : null)
    setEvidenceTab('document')
    setPdfLoading(true)
    setPdfFailed(false)
    setPdfPage(c.page ?? 1)
    setPdfZoom(100)
    try {
      const blob = await api.downloadDocument(c.documentId)
      const url = URL.createObjectURL(blob)
      if (pdfPreview) URL.revokeObjectURL(pdfPreview.url)
      setPdfPreview({ citation: c, url })
    } catch (e) {
      setErrorMsg(errorMessage(e))
      setPdfFailed(true)
    } finally {
      setPdfLoading(false)
    }
  }

  const closePdf = useCallback(() => {
    if (pdfPreview) URL.revokeObjectURL(pdfPreview.url)
    setPdfPreview(null)
    setPdfFailed(false)
  }, [pdfPreview])

  useEffect(() => () => {
    if (pdfPreview) URL.revokeObjectURL(pdfPreview.url)
  }, [pdfPreview])

  useEffect(() => () => {
    streamControllerRef.current?.abort()
    if (renderFrameRef.current != null) window.cancelAnimationFrame(renderFrameRef.current)
  }, [])

  const selectCitation = (index: number) => {
    const citation = citations[index]
    if (citation) void openPdf(citation)
  }

  const copyAnswer = async () => {
    await navigator.clipboard.writeText(answer)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  const navigateEvidenceTabs = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const nextTab = evidenceTab === 'sources' ? 'document' : 'sources'
    setEvidenceTab(nextTab)
    window.requestAnimationFrame(() => document.getElementById(`evidence-tab-${nextTab}`)?.focus())
  }

  const submit = useCallback(
    (event: FormEvent) => {
      event.preventDefault()
      if (!query.trim()) return

      streamControllerRef.current?.abort()
      const controller = new AbortController()
      streamControllerRef.current = controller
      setStreamState('retrieving')
      setAnswer('')
      citationsRef.current = []
      validationPassedRef.current = null
      setCitations([])
      setActiveCitation(null)
      setEvidenceTab('sources')
      closePdf()
      setErrorMsg('')
      setStreamMetrics({})
      answerRef.current = ''
      if (renderFrameRef.current != null) window.cancelAnimationFrame(renderFrameRef.current)
      renderFrameRef.current = null
      requestStartedAtRef.current = performance.now()
      firstTokenRenderedRef.current = false

      const requestId = crypto.randomUUID()
      searchStream(
        {
          query,
          topK,
          sector: sector || undefined,
          missionType: missionType || undefined,
          year: year ? Number(year) : undefined,
          corpusScope: 'PDF',
          requestId,
        },
        (token) => {
          setStreamState('streaming')
          answerRef.current += token
          if (renderFrameRef.current == null) {
            renderFrameRef.current = window.requestAnimationFrame(() => {
              renderFrameRef.current = null
              setAnswer(answerRef.current)
              if (!firstTokenRenderedRef.current && requestStartedAtRef.current != null) {
                firstTokenRenderedRef.current = true
                setStreamMetrics((current) => ({
                  ...current,
                  firstTokenRenderedMs: Math.round(performance.now() - requestStartedAtRef.current!),
                }))
              }
              answerEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
            })
          }
        },
        (citationsData) => {
          if (renderFrameRef.current != null) window.cancelAnimationFrame(renderFrameRef.current)
          renderFrameRef.current = null
          const verifiedCitations = mergeCitations(citationsData as Citation[], citationsRef.current)
          citationsRef.current = verifiedCitations
          setCitations(verifiedCitations)
          const sourceIndexMap = new Map(
            verifiedCitations.map((citation, index) => [citation.sourceIndex ?? index + 1, index + 1]),
          )
          const referencedSources = citationSourceIndexes(answerRef.current)
          const missingSources = referencedSources.filter((sourceIndex) => !sourceIndexMap.has(sourceIndex))
          const sanitizedAnswer = sanitizeGeneratedAnswer(answerRef.current, sourceIndexMap)
          answerRef.current = sanitizedAnswer
          setAnswer(sanitizedAnswer)
          if (validationPassedRef.current === true && referencedSources.length > 0 && (verifiedCitations.length === 0 || missingSources.length > 0)) {
            setErrorMsg('La réponse validée contient des références sans source vérifiée correspondante.')
            setStreamState('error')
            return
          }
          setStreamState('done')
        },
        // onError
        (error) => {
          if (renderFrameRef.current != null) window.cancelAnimationFrame(renderFrameRef.current)
          renderFrameRef.current = null
          answerRef.current = ''
          setAnswer('')
          setErrorMsg(error)
          setStreamState('error')
        },
        (status) => setStreamState(status === 'retrieving' ? 'retrieving' : 'streaming'),
        controller.signal,
        ({ name, valueMs }) => {
          setStreamMetrics((current) => ({
            ...current,
            [name]: Math.round(valueMs),
          }))
        },
        (citationEvents) => {
          const merged = mergeCitations(citationEvents as Citation[], citationsRef.current)
          citationsRef.current = merged
          setCitations(merged)
        },
        undefined,
        ({ passed, diagnostic }) => {
          validationPassedRef.current = passed
          if (!passed) {
            setErrorMsg(diagnostic || 'La réponse générée n’a pas pu être validée à partir des preuves sélectionnées. Réessayez.')
            setStreamState('error')
          }
        },
      )
    },
    [closePdf, query, sector, missionType, topK, year],
  )

  const cancelStream = useCallback(() => {
    if (streamState !== 'retrieving' && streamState !== 'streaming') return
    streamControllerRef.current?.abort()
    streamControllerRef.current = null
    if (renderFrameRef.current != null) window.cancelAnimationFrame(renderFrameRef.current)
    renderFrameRef.current = null
    setStreamState('idle')
    setErrorMsg('')
  }, [streamState])

  const retry = useCallback(() => {
    if (!query.trim()) return
    const form = document.querySelector<HTMLFormElement>('.search-composer')
    form?.requestSubmit()
  }, [query])

  const isStreaming = streamState === 'streaming'
  const isRetrieving = streamState === 'retrieving'
  const hasAnswer = answer.length > 0
  const isDone = streamState === 'done'
  const canDownloadPdf = session?.role === 'ADMIN'
  const isInsufficient = isDone && /information insuffisante|impossible de répondre/i.test(answer)
  const documentSrc = pdfPreview ? `${pdfPreview.url}#page=${pdfPage}&zoom=${pdfZoom}` : ''
  const activeFilterCount = [sector, missionType, year, topK !== 15].filter(Boolean).length
  const processingLabel = isRetrieving ? 'Analyse des sources…' : 'Génération de la réponse…'
  const isLanding = streamState === 'idle' && !hasAnswer

  return (
    <div className={`page page--search ${isLanding ? 'page--search--empty' : ''}`} data-search-layout={isLanding ? 'landing' : 'workspace'}>
      <PageHeader eyebrow="Recherche documentaire" title="Poser une question" description="Formulez une question métier. La réponse n'est produite qu'à partir des extraits réellement retrouvés dans le corpus." />
      <form className="search-composer" onSubmit={submit} aria-busy={isRetrieving || isStreaming}>
        <label className="sr-only" htmlFor="search-question">Votre question</label>
        <div className="search-input-row">
          <textarea id="search-question" rows={3} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Posez votre question…" required />
        </div>
        <div className="search-composer__footer">
          <div className="search-composer__chips">
            <button className="filter-toggle" type="button" aria-expanded={filtersOpen} aria-controls="search-advanced-filters" onClick={() => setFiltersOpen((open) => !open)}><SlidersHorizontal size={15} />Filtres avancés{activeFilterCount > 0 && <span className="filter-toggle__count" aria-label={`${activeFilterCount} filtre${activeFilterCount > 1 ? 's' : ''} actif${activeFilterCount > 1 ? 's' : ''}`}>{activeFilterCount}</span>}</button>
            <span className="search-composer__source-chip"><FileText size={14} />Sources PDF vérifiées</span>
          </div>
          <div className="search-composer__actions">
            <button className="button button--primary search-submit" type="submit" disabled={!query.trim() || isStreaming || isRetrieving} aria-label="Rechercher" title="Rechercher"><ArrowUp size={18} /></button>
          </div>
        </div>
        <div id="search-advanced-filters" className={`filter-row ${filtersOpen ? 'filter-row--open' : ''}`}>
          <label>Secteur<select value={sector} onChange={(event) => setSector(event.target.value)}><option value="">Tous les secteurs</option>{sectors.map((value) => <option key={value}>{value}</option>)}</select></label>
          <label>Type de mission<select value={missionType} onChange={(event) => setMissionType(event.target.value)}><option value="">Tous les types</option>{missionTypes.map((value) => <option key={value}>{value}</option>)}</select></label>
          <label>Année<input type="number" min="2018" max="2030" placeholder="Toutes" value={year} onChange={(event) => setYear(event.target.value)} /></label>
          <label>Profondeur<select value={topK} onChange={(event) => setTopK(Number(event.target.value))}><option value={5}>5 sources</option><option value={10}>10 sources</option><option value={15}>15 sources</option></select></label>
        </div>
      </form>

      {(isRetrieving || (isStreaming && !hasAnswer)) && (
        <div className="stream-status" role="status" aria-live="polite">
          <span className="stream-status__avatar" aria-hidden="true"><img src={logoSrc} alt="" /></span>
          <span className="stream-status__label">{processingLabel}</span>
          <button className="stream-stop" type="button" onClick={cancelStream}><Square size={14} fill="currentColor" /><span>Arrêter la génération</span></button>
        </div>
      )}

      {streamState === 'error' && <div className="search-error"><ErrorState message={errorMsg} /><button className="button button--secondary" type="button" onClick={retry}>Réessayer</button></div>}

      {!hasAnswer && !isRetrieving && streamState !== 'error' && streamState === 'idle' && <EmptySearch />}

      {hasAnswer && (
        <section className="answer-workspace reveal" aria-label="Résultat de recherche">
          <header className="result-summary">
            <div className="result-summary__identity">
              <span className="result-summary__icon"><img src={logoSrc} alt="" /></span>
              <div><span className="eyebrow">Réponse Avaliance</span><h2>Réponse sourcée</h2></div>
            </div>
            <div className="result-summary__metrics">
              <span className={`result-summary__state ${isStreaming ? 'result-summary__state--streaming' : ''}`}><span aria-hidden="true" />{isStreaming ? 'En cours' : 'Terminée'}</span>
              <span className="result-summary__source-count"><FileText size={15} /> {citations.length} {citations.length > 1 ? 'sources' : 'source'}</span>
              {isStreaming && <button className="stream-stop stream-stop--inline" type="button" onClick={cancelStream}><Square size={14} fill="currentColor" /><span>Arrêter la génération</span></button>}
            </div>
          </header>
          <div className="answer-workspace__body">
            <article className="answer-panel">
              {isInsufficient ? (
                <div className="insufficient-callout insufficient-callout--prominent">
                  <div className="insufficient-callout__icon"><AlertTriangle size={28} /></div>
                  <strong>Information insuffisante</strong>
                  <p>Le corpus documentaire ne contient pas de preuve assez pertinente pour répondre à cette question. Essayez de reformuler votre question ou de préciser le contexte (secteur, mission, technologie).</p>
                </div>
              ) : (
                <>
                  <div className="answer-panel__heading"><div><span className="eyebrow">Synthèse</span><h2>Ce que le corpus permet d’établir</h2></div><div className="answer-panel__actions"><button className="icon-button" type="button" onClick={() => void copyAnswer()} title="Copier la réponse" aria-label="Copier la réponse"><Clipboard size={17} /></button><button className="icon-button" type="button" title="Donner un avis" aria-label="Donner un avis"><MessageSquare size={17} /></button></div></div>
                  {copied && <span className="copy-confirmation" role="status">Réponse copiée</span>}
                  <div className="stream-answer">
                    <ReactMarkdown components={{ p: ({ children }) => <p>{renderCitationNodes(children, sourceCardIndexBySourceIndex(citations), selectCitation)}</p>, li: ({ children }) => <li>{renderCitationNodes(children, sourceCardIndexBySourceIndex(citations), selectCitation)}</li> }}>{answer}</ReactMarkdown>
                    {isStreaming && <span className="stream-cursor" aria-hidden="true" />}
                    <div ref={answerEndRef} />
                  </div>
                  {isDone && citations.length > 0 && <div className="answer-footnote"><Quote size={16} /><span>Chaque référence renvoie à un extrait indexé du patrimoine documentaire.</span></div>}
                </>
              )}
            </article>
            {(isDone || isStreaming) && <aside className="evidence-panel">
              <div className="evidence-panel__tabs" role="tablist" aria-label="Preuves de la réponse" onKeyDown={navigateEvidenceTabs}>
                <button id="evidence-tab-sources" className={evidenceTab === 'sources' ? 'is-active' : ''} type="button" role="tab" aria-selected={evidenceTab === 'sources'} aria-controls="evidence-panel-sources" tabIndex={evidenceTab === 'sources' ? 0 : -1} onClick={() => setEvidenceTab('sources')}><FileText size={16} />Sources <span>{citations.length}</span></button>
                <button id="evidence-tab-document" className={evidenceTab === 'document' ? 'is-active' : ''} type="button" role="tab" aria-selected={evidenceTab === 'document'} aria-controls="evidence-panel-document" tabIndex={evidenceTab === 'document' ? 0 : -1} onClick={() => setEvidenceTab('document')}><BookOpenCheck size={16} />Document</button>
              </div>
              {evidenceTab === 'sources' ? <div id="evidence-panel-sources" className="source-list" role="tabpanel" aria-labelledby="evidence-tab-sources">
                {citations.length > 0 ? citations.map((citation, index) => <SourceCard key={citation.citationId ?? `${citation.chunkId}-${citation.sourceIndex ?? index}`} citation={citation} index={index} selected={activeCitation === index} onSelect={() => selectCitation(index)} />) : <div className="evidence-empty"><BookOpenCheck size={22} /><strong>Aucune source exploitable</strong><p>Le corpus ne contient pas de preuve assez pertinente pour cette question.</p></div>}
              </div> : <div id="evidence-panel-document" role="tabpanel" aria-labelledby="evidence-tab-document"><DocumentViewer pdfPreview={pdfPreview} pdfPage={pdfPage} pdfZoom={pdfZoom} pdfLoading={pdfLoading} pdfFailed={pdfFailed} canDownloadPdf={canDownloadPdf} documentSrc={documentSrc} frameRef={pdfFrameRef} onClose={closePdf} onPageChange={setPdfPage} onZoomChange={setPdfZoom} onFullscreen={() => void pdfFrameRef.current?.requestFullscreen()} /></div>}
            </aside>}
          </div>
        </section>
      )}
    </div>
  )
}

function mergeCitations(incoming: Citation[], existing: Citation[] = []): Citation[] {
  const citationsBySource = new Map<string, Citation>()
  for (const citation of [...existing, ...incoming]) {
    const key = citation.citationId ?? `${citation.chunkId}-${citation.sourceIndex ?? ''}`
    citationsBySource.set(key, citation)
  }
  return Array.from(citationsBySource.values())
}

function citationSourceIndexes(value: string): number[] {
  return Array.from(value.matchAll(/\[(\d+)\]/g), (match) => Number(match[1]))
}

function sanitizeGeneratedAnswer(value: string, sourceIndexMap = new Map<number, number>()): string {
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

function sourceCardIndexBySourceIndex(citations: Citation[]): Map<number, number> {
  return new Map(citations.map((citation, cardIndex) => [citation.sourceIndex ?? cardIndex + 1, cardIndex]))
}

function renderCitationNodes(children: ReactNode, sourceCards: Map<number, number>, onSelect: (index: number) => void): ReactNode {
  if (typeof children === 'string') {
    const parts = children.split(/(\[(?:\d+|n)\])/gi)
    return parts.map((part, index) => {
      const match = part.match(/^\[(\d+|n)\]$/i)
      if (!match) return part
      const citationNumber = match[1].toLowerCase() === 'n' ? 1 : Number(match[1])
      const cardIndex = sourceCards.get(citationNumber)
      if (cardIndex == null) return part
      return <button className="citation-chip" type="button" key={`${citationNumber}-${index}`} onClick={() => onSelect(cardIndex)} aria-label={`Ouvrir la source ${citationNumber}`}>[{citationNumber}]</button>
    })
  }
  if (Array.isArray(children)) return children.map((child, index) => <span key={index}>{renderCitationNodes(child, sourceCards, onSelect)}</span>)
  return children
}

function SourceCard({ citation, index, selected, onSelect }: { citation: Citation; index: number; selected: boolean; onSelect: () => void }) {
  const title = citation.documentName ?? citation.missionTitle ?? `Source ${citation.chunkId}`
  return <article className={`source-card ${selected ? 'source-card--selected' : ''}`}>
    <div className="source-card__top"><button className="source-card__number" type="button" onClick={onSelect} aria-label={`Sélectionner la source ${index + 1}`}>[{index + 1}]</button><span className="source-card__label">Preuve retrouvée</span></div>
    <h3 title={title}>{title}</h3>
    <div className="source-card__meta"><span>{citation.page != null ? `Page physique ${citation.page}` : 'Page non précisée'}</span><span>Chunk {citation.chunkId}</span>{citation.missionTitle && <span>{citation.missionTitle}</span>}</div>
    <blockquote>{citation.content}</blockquote>
    <div className="source-card__actions"><button className="link-button" type="button" onClick={onSelect}>Voir dans le document <ArrowUpRight size={15} /></button>{citation.missionId !== null && <Link to={`/missions/${citation.missionId}`}>Ouvrir la mission <ExternalLink size={14} /></Link>}</div>
  </article>
}

function DocumentViewer({ pdfPreview, pdfPage, pdfZoom, pdfLoading, pdfFailed, canDownloadPdf, documentSrc, frameRef, onClose, onPageChange, onZoomChange, onFullscreen }: { pdfPreview: { citation: Citation; url: string } | null; pdfPage: number; pdfZoom: number; pdfLoading: boolean; pdfFailed: boolean; canDownloadPdf: boolean; documentSrc: string; frameRef: { current: HTMLIFrameElement | null }; onClose: () => void; onPageChange: (page: number) => void; onZoomChange: (zoom: number) => void; onFullscreen: () => void }) {
  if (!pdfPreview) return <div className="document-empty" role="tabpanel"><div className="document-empty__icon"><BookOpenCheck size={24} /></div><h3>Choisissez une source</h3><p>La page citée et son extrait apparaîtront ici pour vérification.</p></div>
  const filename = pdfPreview.citation.documentName ?? 'document-source.pdf'
  return <div className="document-viewer" role="tabpanel"><header className="document-viewer__header"><div><span className="eyebrow">Document source</span><h3 title={filename}>{filename}</h3><span>Page physique {pdfPage}</span></div><button className="icon-button" type="button" onClick={onClose} aria-label="Fermer le document" title="Fermer"><X size={17} /></button></header><div className="document-viewer__toolbar"><div className="viewer-controls"><button className="icon-button" type="button" disabled={pdfPage <= 1} onClick={() => onPageChange(Math.max(1, pdfPage - 1))} aria-label="Page précédente" title="Page précédente"><ArrowLeft size={16} /></button><span>Page {pdfPage}</span><button className="icon-button" type="button" onClick={() => onPageChange(pdfPage + 1)} aria-label="Page suivante" title="Page suivante"><ArrowRight size={16} /></button></div><div className="viewer-controls"><button className="icon-button" type="button" disabled={pdfZoom <= 75} onClick={() => onZoomChange(Math.max(75, pdfZoom - 25))} aria-label="Réduire le zoom" title="Réduire le zoom"><ZoomOut size={16} /></button><span>{pdfZoom}%</span><button className="icon-button" type="button" disabled={pdfZoom >= 150} onClick={() => onZoomChange(Math.min(150, pdfZoom + 25))} aria-label="Augmenter le zoom" title="Augmenter le zoom"><ZoomIn size={16} /></button><button className="icon-button" type="button" onClick={onFullscreen} aria-label="Afficher en plein écran" title="Plein écran"><Maximize2 size={16} /></button></div></div>{pdfLoading && <div className="document-viewer__state"><span className="stream-status__dot stream-status__dot--pulse" /> Chargement du document…</div>}{pdfFailed && <div className="document-viewer__state document-viewer__state--error"><AlertTriangle size={18} /> Impossible de charger ce document.</div>}<iframe ref={(node) => { frameRef.current = node }} className="document-viewer__frame" title={filename} src={documentSrc} onError={() => undefined} />{canDownloadPdf && <a className="document-viewer__download" href={pdfPreview.url} download={filename}><Download size={15} /> Télécharger le PDF</a>}</div>
}

function EmptySearch() {
  return (
    <section className="empty-brief">
      <BookOpenCheck size={24} /><span className="eyebrow">Mode d'emploi</span><h2>Une réponse n'a de valeur que si elle reste vérifiable.</h2>
      <p>Décrivez le contexte, le secteur ou la technologie recherchée. Les citations permettent d'ouvrir directement les missions de référence.</p>
      <div><span>01</span><p>Recherche vectorielle et textuelle en parallèle</p><span>02</span><p>Réponse strictement limitée aux preuves retrouvées</p></div>
    </section>
  )
}