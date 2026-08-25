import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { AlertTriangle, ArrowUp, BookOpenCheck, Clipboard, FileText, MessageSquare, Quote, SlidersHorizontal, Square } from 'lucide-react'
import logoSrc from '../assets/logo.png'
import { api, errorMessage, searchStream } from '../api/client.ts'
import { ErrorState } from '../components/AsyncState.tsx'
import { PageHeader } from '../components/PageHeader.tsx'
import { useAuth } from '../auth/auth-context.ts'
import type { Citation } from '../types.ts'
import {
  citationSourceIndexes,
  mergeCitations,
  sanitizeGeneratedAnswer,
} from './search/answer-parsing.ts'
import {
  DocumentViewer,
  EmptySearch,
  SourceCard,
  StructuredAnswer,
} from './search/SearchComponents.tsx'

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
            setErrorMsg(diagnostic || 'La réponse générée n\u2019a pas pu être validée à partir des preuves sélectionnées. Réessayez.')
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
                  <strong>Je ne trouve pas encore de preuve exploitable</strong><p>J'ai parcouru les PDF vérifiés, mais aucune preuve suffisamment précise n'a été confirmée pour répondre sans risque d'inventer. Essayez de préciser le projet, le périmètre ou le type d'information recherché.</p>
                </div>
              ) : (
                <>
                  <div className="answer-panel__heading"><div><span className="eyebrow">Réponse sourcée</span><h2>Ce que les documents permettent d'établir</h2><p className="answer-panel__subtitle">Une synthèse concise, construite uniquement à partir des PDF vérifiés.</p></div><div className="answer-panel__actions"><button className="icon-button" type="button" onClick={() => void copyAnswer()} title="Copier la réponse" aria-label="Copier la réponse"><Clipboard size={17} /></button><button className="icon-button" type="button" title="Donner un avis" aria-label="Donner un avis"><MessageSquare size={17} /></button></div></div>
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