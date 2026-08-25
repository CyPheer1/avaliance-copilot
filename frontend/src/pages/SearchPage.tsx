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
              <div><span className="eyebrow">Assistant documentaire</span><h2>Réponse</h2></div>
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
                  <strong>Je ne trouve pas encore de preuve exploitable</strong><p>J’ai parcouru les PDF vérifiés, mais aucune preuve suffisamment précise n’a été confirmée pour répondre sans risque d’inventer. Essayez de préciser le projet, le périmètre ou le type d’information recherché.</p>
                </div>
              ) : (
                <>
                  <div className="answer-panel__heading"><div><span className="eyebrow">Réponse sourcée</span><h2>Ce que les documents permettent d’établir</h2><p className="answer-panel__subtitle">Une synthèse concise, construite uniquement à partir des PDF vérifiés.</p></div><div className="answer-panel__actions"><button className="icon-button" type="button" onClick={() => void copyAnswer()} title="Copier la réponse" aria-label="Copier la réponse"><Clipboard size={17} /></button><button className="icon-button" type="button" title="Donner un avis" aria-label="Donner un avis"><MessageSquare size={17} /></button></div></div>
                  {copied && <span className="copy-confirmation" role="status">Réponse copiée</span>}
                  <div className="stream-answer">
                    <StructuredAnswer query={query} answer={answer} citations={citations} onSelect={selectCitation} />
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

function decodeAnswerEntities(value: string): string {
  return value
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
}

function renderCitationNodes(children: ReactNode, sourceCards: Map<number, number>, onSelect: (index: number) => void): ReactNode {
  if (typeof children === 'string') {
    const parts = decodeAnswerEntities(children).split(/(\[(?:\d+|n)\])/gi)
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


type AnswerMode = 'identity' | 'team' | 'budget' | 'scope' | 'objectives' | 'summary' | 'metrics' | 'architecture' | 'default'

type MetricRow = { indicator: string; before: string; after: string; evolution: string; target: string }
type ArchitectureRow = { layer: string; components: string; justification: string; citation: string }

function foldAnswerText(value: string): string {
  return value.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
}

function detectAnswerMode(query: string): AnswerMode {
  const folded = foldAnswerText(query)
  if (folded.includes('fiche') && (folded.includes('identite') || folded.includes('complete'))) return 'identity'
  if (folded.includes('equipe') && (folded.includes('quelle') || folded.includes('composition') || folded.includes('projet'))) return 'team'
  if (folded.includes('budget')) return 'budget'
  if (folded.includes('perimetre') && (folded.includes('exclu') || folded.includes('hors') || folded.includes('non inclus'))) return 'scope'
  if (folded.includes('objectif') && folded.includes('technique')) return 'objectives'
  if (folded.includes('resultat mesure') || folded.includes('resultats mesures') || folded.includes('indicateur')) return 'metrics'
  if (folded.includes('probleme initial') && folded.includes('solution') && (folded.includes('resultat') || folded.includes('impact'))) return 'summary'
  if (folded.includes('architecture') || folded.includes('choix technique') || folded.includes('mesures de securite') || folded.includes('technologie')) return 'architecture'
  return 'default'
}

function splitAnswerBlocks(value: string): string[] {
  const cleaned = decodeAnswerEntities(value)
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\s+(?=##\s)/g, '\n\n')
    .replace(/;\s+-\s+(?=[A-ZÀ-ÖØ-Þ0-9])/g, ';\n- ')
  return cleaned.split(/\n{2,}/).map((part) => part.trim()).filter(Boolean)
}

function identityValues(_query: string, answer: string): string[] {
  const segments = answer.replace(/\s+\[(\d+)\]/g, ' [$1]\n').split(/\n+/).map((value) => value.trim()).filter(Boolean)
  return segments.slice(0, 6).map((segment) => {
    const value = segment
      .replace(/^(?:CLIENT|SECTEUR):\s*(?:TYPE DE MISSION|PÉRIODE|BUDGET CONSOMMÉ|ÉQUIPE|RÉFÉRENCE|STATUT)\s*;\s*[^:;]+:\s*/i, '')
      .replace(/^(?:CLIENT|SECTEUR|TYPE DE MISSION|PÉRIODE|BUDGET CONSOMMÉ|ÉQUIPE|RÉFÉRENCE|STATUT)\s*:\s*/i, '')
      .replace(/^[^:;]{2,80}:\s*/, '')
      .trim()
    return value
  }).filter(Boolean)
}

function metricRows(answer: string): MetricRow[] {
  const rows: MetricRow[] = []
  const pattern = /Indicateur:\s*(.*?);\s*Avant:\s*(.*?);\s*Après:\s*(.*?);\s*Évolution:\s*(.*?);\s*Cible:\s*(.*?)(?=\s+Indicateur:|$)/gi
  for (const match of answer.matchAll(pattern)) {
    rows.push({ indicator: match[1].trim(), before: match[2].trim(), after: match[3].trim(), evolution: match[4].trim(), target: match[5].trim() })
  }
  return rows
}

function objectiveRows(answer: string): Array<{ text: string; citation: string }> {
  const rows: Array<{ text: string; citation: string }> = []
  const pattern = /^\s*-\s+(.+?)\s+\[(\d+)\]\s*$/gm
  for (const match of answer.matchAll(pattern)) rows.push({ text: match[1].trim(), citation: `[${match[2]}]` })
  return rows
}

function architectureRows(blocks: string[]): ArchitectureRow[] {
  const rows: ArchitectureRow[] = []
  const pattern = /Couche:\s*(.*?);\s*Composants retenus:\s*(.*?);\s*Justification:\s*(.*?)(?=\s+Couche:|\s+##|$)/gi
  for (const block of blocks) {
    const citation = block.match(/\[(\d+)\]\s*$/)?.[0] ?? ''
    for (const match of block.matchAll(pattern)) {
      rows.push({ layer: match[1].trim(), components: match[2].trim(), justification: match[3].trim(), citation })
    }
  }
  return rows
}

function summaryGroups(blocks: string[]): Array<{ label: string; blocks: string[] }> {
  const groups: Array<{ label: string; blocks: string[] }> = [
    { label: 'Contexte et problème initial', blocks: [] },
    { label: 'Solution retenue', blocks: [] },
    { label: 'Résultats établis', blocks: [] },
  ]
  for (const block of blocks) {
    const folded = foldAnswerText(block)
    if (/(a la cloture|six mois|atteint|diminu|recul|resultat|adoption|disponibilite)/.test(folded)) groups[2].blocks.push(block)
    else if (/(solution|cible|plateforme|feder|fhir|wms cloud|moteur)/.test(folded)) groups[1].blocks.push(block)
    else groups[0].blocks.push(block)
  }
  return groups.filter((group) => group.blocks.length > 0)
}

type BudgetRow = { label: string; amount: string; share: string }

function budgetRows(answer: string): BudgetRow[] {
  const rows: BudgetRow[] = []
  const pattern = /Rubrique:\s*(.*?);\s*Montant HT:\s*(.*?);\s*Part:\s*([^\s]+%)/gi
  for (const match of answer.matchAll(pattern)) rows.push({ label: match[1].trim(), amount: match[2].trim(), share: match[3].trim() })
  return rows
}

function cleanAnswerBlock(value: string): string {
  return decodeAnswerEntities(value)
    .replace(/^#{1,6}\s+[^\n]+(?:\n|$)/, '')
    .replace(/^(?:CLIENT|SECTEUR):\s*[^\n]+(?:\n|$)/i, '')
    .trim()
}

function MarkdownAnswer({ answer, sourceCards, onSelect }: { answer: string; sourceCards: Map<number, number>; onSelect: (index: number) => void }) {
  return <ReactMarkdown components={{
    p: ({ children }) => <p>{renderCitationNodes(children, sourceCards, onSelect)}</p>,
    li: ({ children }) => <li>{renderCitationNodes(children, sourceCards, onSelect)}</li>,
    h1: ({ children }) => <h3>{children}</h3>,
    h2: ({ children }) => <h3>{children}</h3>,
    h3: ({ children }) => <h4>{children}</h4>,
  }}>{decodeAnswerEntities(answer)}</ReactMarkdown>
}

function StructuredAnswer({ query, answer, citations, onSelect }: { query: string; answer: string; citations: Citation[]; onSelect: (index: number) => void }) {
  const sourceCards = sourceCardIndexBySourceIndex(citations)
  const blocks = splitAnswerBlocks(answer)
  const mode = detectAnswerMode(query)
  const renderEvidence = (value: string, index: number, className = '') => (
    <p className={className} key={`${index}-${value.slice(0, 24)}`}>{renderCitationNodes(cleanAnswerBlock(value), sourceCards, onSelect)}</p>
  )

  if (mode === 'identity') {
    const values = identityValues(query, answer)
    const labels = ['Mission', 'Période', 'Budget consommé', 'Équipe', 'Référence', 'Statut']
    if (values.length >= 4) {
      const projectContext = query.match(/projet\s+(.+?)(?::|\s+—)/i)?.[1]?.trim()
      return <div className="answer-structured answer-structured--identity">
        {projectContext && <div className="answer-context-line"><span>Projet demandé</span><strong>{projectContext}</strong></div>}
        <div className="answer-fact-grid">{values.map((value, index) => <div className="answer-fact-card" key={`${labels[index] ?? 'fait'}-${index}`}><span className="answer-fact-card__label">{labels[index] ?? 'Fait établi'}</span><div>{renderCitationNodes(value, sourceCards, onSelect)}</div></div>)}</div>
      </div>
    }
  }

  if (mode === 'team') {
    const match = answer.match(/(\d+\s+personnes\s*\([^)]*\))/i)
    const value = match?.[1] ?? cleanAnswerBlock(answer)
    return <div className="answer-structured answer-structured--field"><div className="answer-structured__eyebrow">Équipe mobilisée</div><section className="answer-fact-card answer-fact-card--wide"><span className="answer-fact-card__label">Composition de l’équipe</span><div>Le projet a mobilisé {renderCitationNodes(`${value} [1]`, sourceCards, onSelect)}</div></section></div>
  }

  if (mode === 'budget') {
    const rows = budgetRows(answer)
    if (rows.length > 0) return <div className="answer-structured answer-structured--budget"><div className="answer-structured__eyebrow">Répartition budgétaire</div><div className="answer-table-wrap"><table className="answer-facts-table"><thead><tr><th>Rubrique</th><th>Montant HT</th><th>Part</th></tr></thead><tbody>{rows.map((row, index) => <tr key={`${row.label}-${index}`}><td>{row.label}</td><td>{renderCitationNodes(`${row.amount} [1]`, sourceCards, onSelect)}</td><td>{renderCitationNodes(`${row.share} [1]`, sourceCards, onSelect)}</td></tr>)}</tbody></table></div></div>
  }

  if (mode === 'scope') {
    return <div className="answer-structured answer-structured--scope"><div className="answer-structured__eyebrow">Périmètre exclu</div><section className="answer-summary-card"><h3>Ce qui n’était pas inclus</h3>{blocks.map((block, index) => renderEvidence(block, index))}</section></div>
  }

  if (mode === 'objectives') {
    const rows = objectiveRows(answer)
    if (rows.length > 0) return <div className="answer-structured answer-structured--objectives"><div className="answer-structured__eyebrow">Objectifs techniques</div><section className="answer-summary-card"><h3>Ce que la cible devait garantir</h3><ul>{rows.map((row, index) => <li key={`${index}-${row.text.slice(0, 24)}`}>{renderCitationNodes(`${row.text} ${row.citation}`, sourceCards, onSelect)}</li>)}</ul></section></div>
  }

  if (mode === 'metrics') {
    const rows = metricRows(answer)
    if (rows.length > 0) {
      return <div className="answer-structured answer-structured--metrics"><div className="answer-structured__eyebrow">Indicateurs retrouvés</div><div className="answer-table-wrap"><table className="answer-facts-table"><thead><tr><th>Indicateur</th><th>Avant</th><th>Après</th><th>Évolution</th><th>Cible</th></tr></thead><tbody>{rows.map((row, index) => <tr key={`${row.indicator}-${index}`}><td>{renderCitationNodes(row.indicator, sourceCards, onSelect)}</td><td>{renderCitationNodes(row.before, sourceCards, onSelect)}</td><td>{renderCitationNodes(row.after, sourceCards, onSelect)}</td><td>{renderCitationNodes(row.evolution, sourceCards, onSelect)}</td><td>{renderCitationNodes(row.target, sourceCards, onSelect)}</td></tr>)}</tbody></table></div></div>
    }
  }

  if (mode === 'summary') {
    const groups = summaryGroups(blocks)
    if (groups.length >= 2) return <div className="answer-structured answer-structured--summary">{groups.map((group) => <section className="answer-summary-card" key={group.label}><h3>{group.label}</h3>{group.blocks.map((block, index) => renderEvidence(block, index))}</section>)}</div>
  }

  if (mode === 'architecture') {
    const rows = architectureRows(blocks)
    const securityBlocks = blocks.filter((block) => !/Couche:/i.test(block) && /(sécurité|mfa|chiffrement|certificat|journal|contrôle d’accès|accès par rôle|conformité)/i.test(block))
    if (rows.length > 0) return <div className="answer-structured answer-structured--architecture"><div className="answer-structured__eyebrow">Architecture retenue</div><div className="answer-table-wrap"><table className="answer-facts-table answer-architecture-table"><thead><tr><th>Couche</th><th>Composants retenus</th><th>Justification</th></tr></thead><tbody>{rows.map((row, index) => <tr key={`${row.layer}-${index}`}><td>{row.layer}</td><td>{renderCitationNodes(`${row.components} ${row.citation}`, sourceCards, onSelect)}</td><td>{renderCitationNodes(`${row.justification} ${row.citation}`, sourceCards, onSelect)}</td></tr>)}</tbody></table></div>{securityBlocks.length > 0 && <section className="answer-security-card"><h3>Sécurité et conformité</h3>{securityBlocks.map((block, index) => renderEvidence(block, index, 'answer-security-card__text'))}</section>}</div>
    return <div className="answer-structured answer-structured--architecture"><div className="answer-structured__eyebrow">Éléments techniques retrouvés</div>{blocks.map((block, index) => <div className="answer-evidence-block" key={`${index}-${block.slice(0, 24)}`}>{renderEvidence(block, index)}</div>)}</div>
  }

  return <div className="answer-structured answer-structured--default"><MarkdownAnswer answer={answer} sourceCards={sourceCards} onSelect={onSelect} /></div>
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