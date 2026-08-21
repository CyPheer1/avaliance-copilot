import type { ApiErrorBody, AuthSession, DashboardSummary, Mission, MissionPage, RegisterUserRequest, RfpJob, RfpResponse, SearchRequest, SearchResponse, SourceDocument, SourceDocumentPage, UserAccount } from '../types.ts'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'
const SESSION_KEY = 'avaliance-copilot-session'
const AUTH_REQUEST_TIMEOUT_MS = 15_000
// The synchronous RFP pipeline has a 180 s server budget (including a possible
// cold-model Call A); retain margin for reverse-proxy and response serialization.
const RFP_REQUEST_TIMEOUT_MS = 330_000

export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function parseRfpResponse(value: unknown): RfpResponse {
  const root = asRecord(value)
  const proposal = asRecord(root?.proposal)
  const sections = Array.isArray(proposal?.sections) ? proposal.sections : null
  const requestId = root?.requestId ?? root?.request_id
  if (!root || typeof requestId !== 'string' || !requestId || !proposal || !sections) {
    throw new ApiError('La réponse de proposition est invalide ou incomplète. Réessayez.', 502)
  }
  const safeSections = sections ?? []

  const rawSources = root.sources
  const parsedSources: RfpResponse['sources'] = Array.isArray(rawSources)
    ? rawSources.flatMap((val) => {
        const s = asRecord(val)
        if (!s || typeof s.id !== 'string' || typeof s.title !== 'string') return []
        return [
          {
            id: s.id,
            type: (s.type as 'brief' | 'internal_pdf' | 'web') || 'internal_pdf',
            title: s.title,
            documentId: (s.documentId ?? s.document_id) as number | undefined,
            documentName: (s.documentName ?? s.document_name) as string | undefined,
            page: s.page as number | undefined,
            chunkId: (s.chunkId ?? s.chunk_id) as number | undefined,
            excerpt: s.excerpt as string | undefined,
            url: s.url as string | undefined,
            publisher: s.publisher as string | undefined,
            score: s.score as number | undefined,
          },
        ]
      })
    : []

  const rawQuality = asRecord(root.quality)
  const parsedQuality = rawQuality
    ? {
        passed: rawQuality.passed === true,
        score: typeof rawQuality.score === 'number' ? rawQuality.score : undefined,
        coverageScore: typeof (rawQuality.coverageScore ?? rawQuality.coverage_score) === 'number' ? ((rawQuality.coverageScore ?? rawQuality.coverage_score) as number) : undefined,
        citationIntegrity: typeof (rawQuality.citationIntegrity ?? rawQuality.citation_integrity) === 'number' ? ((rawQuality.citationIntegrity ?? rawQuality.citation_integrity) as number) : undefined,
        sectionCount: typeof (rawQuality.sectionCount ?? rawQuality.section_count) === 'number' ? ((rawQuality.sectionCount ?? rawQuality.section_count) as number) : undefined,
        generationMode: (rawQuality.generationMode ?? rawQuality.generation_mode) as any,
        plannerMode: (rawQuality.plannerMode ?? rawQuality.planner_mode) as any,
        extractionMode: (rawQuality.extractionMode ?? rawQuality.extraction_mode) as any,
        repairAttempted: Boolean(rawQuality.repairAttempted ?? rawQuality.repair_attempted),
        failedClusterKeys: strings(rawQuality.failedClusterKeys ?? rawQuality.failed_cluster_keys),
        coverageDetail: typeof (rawQuality.coverageDetail ?? rawQuality.coverage_detail) === 'number' ? ((rawQuality.coverageDetail ?? rawQuality.coverage_detail) as number) : undefined,
        provenanceDetail: typeof (rawQuality.provenanceDetail ?? rawQuality.provenance_detail) === 'number' ? ((rawQuality.provenanceDetail ?? rawQuality.provenance_detail) as number) : undefined,
        specificityDetail: typeof (rawQuality.specificityDetail ?? rawQuality.specificity_detail) === 'number' ? ((rawQuality.specificityDetail ?? rawQuality.specificity_detail) as number) : undefined,
        solutionQualityDetail: typeof (rawQuality.solutionQualityDetail ?? rawQuality.solution_quality_detail) === 'number' ? ((rawQuality.solutionQualityDetail ?? rawQuality.solution_quality_detail) as number) : undefined,
        governanceDetail: typeof (rawQuality.governanceDetail ?? rawQuality.governance_detail) === 'number' ? ((rawQuality.governanceDetail ?? rawQuality.governance_detail) as number) : undefined,
        writingDetail: typeof (rawQuality.writingDetail ?? rawQuality.writing_detail) === 'number' ? ((rawQuality.writingDetail ?? rawQuality.writing_detail) as number) : undefined,
        sourceQualityDetail: typeof (rawQuality.sourceQualityDetail ?? rawQuality.source_quality_detail) === 'number' ? ((rawQuality.sourceQualityDetail ?? rawQuality.source_quality_detail) as number) : undefined,
        warnings: strings(rawQuality.warnings),
      }
    : undefined

  const rawClusterMetrics = Array.isArray(root.cluster_metrics ?? root.clusterMetrics)
    ? ((root.cluster_metrics ?? root.clusterMetrics) as unknown[])
    : []
  const clusterMetrics = rawClusterMetrics.map((cm) => {
    const r = asRecord(cm) ?? {}
    return {
      clusterKeys: strings(r.clusterKeys ?? r.cluster_keys),
      mode: (r.mode === 'deterministic_fallback' ? 'deterministic_fallback' : 'llm') as 'llm' | 'deterministic_fallback',
      durationMs: typeof (r.durationMs ?? r.duration_ms) === 'number' ? ((r.durationMs ?? r.duration_ms) as number) : 0,
      warningCode: typeof (r.warningCode ?? r.warning_code) === 'string' ? ((r.warningCode ?? r.warning_code) as string) : null,
    }
  })

  return {
    requestId: typeof requestId === 'string' ? requestId : undefined,
    mode: typeof root.mode === 'string' ? (root.mode as 'full' | 'standard' | 'brief') : 'standard',
    status: typeof root.status === 'string' ? (root.status as 'completed' | 'failed' | 'pending') : 'completed',
    requirements: (asRecord(root.requirements) ?? {}) as unknown as RfpResponse['requirements'],
    proposal: {
      title: typeof proposal?.title === 'string' ? proposal.title : 'Proposition de réponse',
      executiveSummary: typeof (proposal?.executiveSummary ?? proposal?.executive_summary) === 'string' ? ((proposal?.executiveSummary ?? proposal?.executive_summary) as string) : undefined,
      legacyMarkdown: undefined,
      sections: safeSections.map((value, index) => {
        const section = asRecord(value)
        if (!section || typeof section.title !== 'string') {
          throw new ApiError(`La section ${index + 1} de la proposition est invalide. Réessayez.`, 502)
        }
        const rawClaims = section.claims
        const claimsList: unknown[] = Array.isArray(rawClaims) ? rawClaims : []
        const parsedClaims = claimsList.flatMap((item) => {
          const c = asRecord(item)
          if (!c || typeof c.text !== 'string') return []
          const rawIndexes = c.citationIndexes ?? c.citation_indexes
          const indexes: unknown[] = Array.isArray(rawIndexes) ? rawIndexes : []
          return [
            {
              id: typeof c.id === 'string' ? c.id : undefined,
              text: c.text,
              kind: (c.kind as any) || 'recommendation',
              sourceIds: strings(c.sourceIds ?? c.source_ids),
              citationIndexes: indexes.filter((n): n is number => typeof n === 'number'),
              confidence: typeof c.confidence === 'number' ? c.confidence : 1.0,
            },
          ]
        })

        const rawTables = section.tables
        const tables: unknown[] = Array.isArray(rawTables) ? rawTables : []

        return {
          key: typeof section.key === 'string' ? section.key : `section-${index + 1}`,
          order: typeof section.order === 'number' ? section.order : index + 1,
          title: section.title,
          status: (section.status as any) || 'complete',
          statusReason: typeof (section.statusReason ?? section.status_reason) === 'string' ? ((section.statusReason ?? section.status_reason) as string) : undefined,
          summary: typeof section.summary === 'string' ? section.summary : undefined,
          body: typeof section.body === 'string' ? section.body : undefined,
          narrative: strings(section.narrative),
          claims: parsedClaims,
          bullets: Array.isArray(section.bullets) ? section.bullets.flatMap(b => {
             if (typeof b === 'string') return [{ text: b }]
             const obj = asRecord(b)
             if (!obj || typeof obj.text !== 'string') return []
             const anchor = asRecord(obj.anchor)
             return [{
               text: obj.text,
               anchor: anchor ? {
                 type: (anchor.type as any) || 'fact',
                 id: typeof anchor.id === 'string' ? anchor.id : undefined
               } : undefined
             }]
          }) : [],
          questions: strings(section.questions),
          factsFromBrief: strings(section.factsFromBrief ?? section.facts_from_brief),
          verifiedReferences: (Array.isArray(section.verifiedReferences ?? section.verified_references)
            ? (section.verifiedReferences ?? section.verified_references) as unknown[]
            : []
          ).flatMap((item) => {
            const c = asRecord(item)
            if (!c || typeof c.text !== 'string') return []
            const rawIndexes = c.citationIndexes ?? c.citation_indexes
            const indexes: unknown[] = Array.isArray(rawIndexes) ? rawIndexes : []
            return typeof c.text === 'string'
              ? [{
                id: typeof c.id === 'string' ? c.id : undefined,
                text: c.text,
                kind: (c.kind as any) || 'internal_evidence',
                sourceIds: strings(c.sourceIds ?? c.source_ids),
                citationIndexes: indexes.filter((n): n is number => typeof n === 'number'),
                confidence: typeof c.confidence === 'number' ? c.confidence : 1.0,
              }]
              : []
          }),
          recommendations: strings(section.recommendations),
          assumptions: strings(section.assumptions),
          assumptionsToConfirm: strings(section.assumptionsToConfirm ?? section.assumptions_to_confirm),
          evidence: Array.isArray(section.evidence) ? section.evidence.map(e => asRecord(e) as any) : [],
          tables: tables.flatMap((item) => {
            const table = asRecord(item)
            const rows: unknown[] = Array.isArray(table?.rows) ? table.rows : []
            return table && typeof table.title === 'string'
              ? [{ title: table.title, columns: strings(table.columns), rows: rows.map(strings) }]
              : []
          }),
        }
      }),
    },
    sources: parsedSources,
    citations: Array.isArray(root.citations) ? root.citations.flatMap((value) => {
      const citation = asRecord(value)
      const citationId = citation?.citationId ?? citation?.citation_id
      const chunkId = citation?.chunkId ?? citation?.chunk_id
      const documentId = citation?.documentId ?? citation?.document_id
      const documentName = citation?.documentName ?? citation?.document_name
      const sourceIndex = citation?.sourceIndex ?? citation?.source_index
      return typeof citationId === 'string' && typeof chunkId === 'number' && typeof documentId === 'number' && typeof documentName === 'string' && typeof citation?.page === 'number' && typeof citation.content === 'string' && typeof sourceIndex === 'number'
        ? [{ citationId, chunkId, documentId, documentName, page: citation.page, content: citation.content, sourceIndex } as RfpResponse['citations'][number]] : []
    }) : [],
    clusterMetrics,
    similarMissions: (() => {
      const rawMissions = root.similarMissions ?? root.similar_missions
      const missions: unknown[] = Array.isArray(rawMissions) ? rawMissions : []
      return missions.flatMap((value) => {
        const mission = asRecord(value)
        const rawScore = asRecord(mission?.scoreBreakdown ?? mission?.score_breakdown)
        const score = (field: string) => typeof rawScore?.[field] === 'number' ? rawScore[field] : undefined
        const finalScore = score('finalScore') ?? score('final_score')
        return mission && typeof mission.id === 'number' && typeof mission.title === 'string' && finalScore !== undefined
          ? [{
            id: mission.id,
            title: mission.title,
            sector: typeof mission.sector === 'string' ? mission.sector : 'Non précisé',
            missionType: typeof (mission.missionType ?? mission.mission_type) === 'string' ? (mission.missionType ?? mission.mission_type) as string : undefined,
            technologies: strings(mission.technologies),
            year: typeof mission.year === 'number' ? mission.year : 0,
            summary: typeof mission.summary === 'string' ? mission.summary : '',
              scoreBreakdown: {
                sectorMatch: score('sectorMatch') ?? score('sector_match') ?? 0,
                projectTypeMatch: score('projectTypeMatch') ?? score('project_type_match') ?? 0,
                businessNeedMatch: score('businessNeedMatch') ?? score('business_need_match') ?? 0,
                constraintMatch: score('constraintMatch') ?? score('constraint_match') ?? 0,
                technologyMatch: score('technologyMatch') ?? score('technology_match') ?? 0,
                finalScore,
              },
            }] : []
      })
    })(),
    evidenceValidationPassed: root.evidenceValidationPassed === true || root.evidence_validation_passed === true,
    quality: parsedQuality,
    diagnostic: typeof (root.diagnostic ?? root.evidence_diagnostic) === 'string' ? (root.diagnostic ?? root.evidence_diagnostic) as string : null,
  }
}

export function readSession(): AuthSession | null {
  const value = localStorage.getItem(SESSION_KEY)
  if (!value) return null
  try {
    return JSON.parse(value) as AuthSession
  } catch {
    localStorage.removeItem(SESSION_KEY)
    return null
  }
}

export function writeSession(session: AuthSession | null) {
  if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session))
  else localStorage.removeItem(SESSION_KEY)
}

async function request<T>(path: string, init?: RequestInit, timeoutMs?: number): Promise<T> {
  const session = readSession()
  const headers = new Headers(init?.headers)
  headers.set('Accept', 'application/json')
  if (init?.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (session) headers.set('Authorization', `Bearer ${session.token}`)

  const requestId = headers.get('X-Request-Id') ?? headers.get('X-Request-ID') ?? crypto.randomUUID()
  headers.set('X-Request-Id', requestId)

  const timeoutController = timeoutMs === undefined ? undefined : new AbortController()
  const timeoutId = timeoutController === undefined ? undefined : window.setTimeout(() => timeoutController.abort(), timeoutMs)
  const signal = timeoutController === undefined
    ? init?.signal
    : init?.signal
      ? AbortSignal.any([init.signal, timeoutController.signal])
      : timeoutController.signal

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers, signal })
    if (response.status === 401 || response.status === 403) {
      writeSession(null)
      window.dispatchEvent(new Event('avaliance:session-expired'))
    }
    if (!response.ok) {
      const respRequestId = response.headers.get('X-Request-Id') ?? response.headers.get('X-Request-ID') ?? requestId
      const body = await response.json().catch(() => ({})) as ApiErrorBody & { detail?: string }
      const errorDetail = body.message ?? body.error ?? body.detail ?? (
        response.status === 401 ? 'Identifiant ou mot de passe incorrect.' :
        response.status === 403 ? 'Accès refusé. Vérifiez l’adresse du frontend et les origines CORS autorisées.' :
        response.status === 504 ? 'Délai d’attente Nginx/Passerelle dépassé (HTTP 504).' :
        response.status === 503 ? 'Service IA temporairement indisponible (HTTP 503).' :
        response.status === 502 ? 'Erreur de communication avec le service IA (HTTP 502 Bad Gateway).' :
        `Le service a retourné une erreur HTTP ${response.status}.`
      )
      throw new ApiError(`${errorDetail} [Request ID: ${respRequestId}]`, response.status)
    }
    if (response.status === 204) return undefined as T
    return await response.json() as T
  } catch (error) {
    if (timeoutController?.signal.aborted) {
      throw new ApiError(`Erreur de connexion : le délai maximal (${timeoutMs ? timeoutMs / 1000 : 0}s) a expiré [Request ID: ${requestId}].`, 0)
    }
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(`Erreur de connexion : la requête a été interrompue (browser AbortError) [Request ID: ${requestId}].`, 0)
    }
    const cause = error instanceof Error ? error.message : String(error)
    throw new ApiError(`Erreur de connexion : échec de communication (${cause}) [Request ID: ${requestId}].`, 0)
  } finally {
    if (timeoutId !== undefined) window.clearTimeout(timeoutId)
  }
}

async function download(path: string): Promise<Blob> {
  const session = readSession()
  const headers = new Headers()
  if (session) headers.set('Authorization', `Bearer ${session.token}`)
  const response = await fetch(`${API_BASE_URL}${path}`, { headers }).catch(() => {
    throw new ApiError('Le service est indisponible. Vérifiez que la plateforme est démarrée.', 0)
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as ApiErrorBody
    throw new ApiError(body.message ?? body.error ?? `Le téléchargement a échoué (HTTP ${response.status}).`, response.status)
  }
  return response.blob()
}

export const api = {
  login: (username: string, password: string) => request<AuthSession>('/auth/login', {
    method: 'POST', body: JSON.stringify({ username, password }),
  }, AUTH_REQUEST_TIMEOUT_MS),
  users: () => request<UserAccount[]>('/auth/users'),
  registerUser: (payload: RegisterUserRequest) => request<{ message: string; username: string }>('/auth/register', {
    method: 'POST', body: JSON.stringify(payload),
  }),
  dashboard: (days = 30) => request<DashboardSummary>(`/dashboard/summary?days=${days}`),
  search: (payload: SearchRequest) => request<SearchResponse>('/search', {
    method: 'POST', body: JSON.stringify(payload),
  }),
  generateRfp: async (payload: { description: string; mode?: string; sector?: string; requestId?: string }) => {
    const requestId = payload.requestId ?? crypto.randomUUID()
    const response = await request<unknown>('/rfp/generate', {
      method: 'POST',
      headers: { 'X-Request-Id': requestId },
      body: JSON.stringify({ requestId, description: payload.description, mode: payload.mode || 'standard', sector: payload.sector }),
    }, RFP_REQUEST_TIMEOUT_MS)
    return parseRfpResponse(response)
  },
  createRfpJob: (payload: { description: string; sector?: string }) => request<{ jobId: string; status: RfpJob['status']; requestId: string }>('/rfp/jobs', {
    method: 'POST', body: JSON.stringify({ description: payload.description, mode: 'full', sector: payload.sector }),
  }, AUTH_REQUEST_TIMEOUT_MS),
  rfpJob: (jobId: string) => request<RfpJob>(`/rfp/jobs/${jobId}`),
  rfpJobResult: async (jobId: string) => parseRfpResponse(await request<unknown>(`/rfp/jobs/${jobId}/result`)),
  cancelRfpJob: (jobId: string) => request<RfpJob>(`/rfp/jobs/${jobId}/cancel`, { method: 'POST' }),
  missions: (params: URLSearchParams) => request<MissionPage>(`/missions?${params.toString()}`),
  mission: (id: number) => request<Mission>(`/missions/${id}`),
  documents: (params: URLSearchParams) => request<SourceDocumentPage>(`/documents?${params.toString()}`),
  uploadDocument: (file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<SourceDocument>('/documents', { method: 'POST', body })
  },
  retryDocument: (id: number) => request<SourceDocument>(`/documents/${id}/index`, { method: 'POST' }),
  deleteDocument: (id: number) => request<void>(`/documents/${id}`, { method: 'DELETE' }),
  downloadDocument: (id: number) => download(`/documents/${id}/content`),
}

/**
 * Stream a search response via SSE. Tokens arrive one-by-one for real-time display.
 * @param payload  - Same SearchRequest as the non-streaming endpoint.
 * @param onToken  - Called for each token (word fragment) as it is generated.
 * @param onDone   - Called once when generation is complete, with citations and confidence.
 * @param onError  - Called if an error occurs.
 * @param onStatus - Called when retrieval or generation starts.
 */
export async function searchStream(
  payload: { query: string; topK?: number; sector?: string; missionType?: string; year?: number; corpusScope?: 'PDF' | 'MISSION' | 'LEGACY_SYNTHETIC'; requestId?: string },
  onToken: (token: string) => void,
  onDone: (citations: Array<{
    citationId?: string | null; requestId?: string | null;
    chunkId: number; missionId: number | null; missionTitle: string | null;
    documentId: number | null; documentName: string | null; page: number | null;
    corpusScope?: 'PDF' | 'MISSION' | 'LEGACY_SYNTHETIC' | null;
    content: string; score: number; rrfScore?: number | null; relevanceScore?: number | null; sourceIndex?: number;
  }>, confidence: number) => void,
  onError: (error: string) => void,
  onStatus?: (status: 'retrieving' | 'generating') => void,
  signal?: AbortSignal,
  onMetric?: (metric: { name: string; valueMs: number }) => void,
  onCitation?: (citations: Array<{
    citationId?: string | null; requestId?: string | null;
    chunkId: number; missionId: number | null; missionTitle: string | null;
    documentId: number | null; documentName: string | null; page: number | null;
    corpusScope?: 'PDF' | 'MISSION' | 'LEGACY_SYNTHETIC' | null;
    content: string; score: number; rrfScore?: number | null; relevanceScore?: number | null; sourceIndex?: number;
  }>) => void,
  onEvidence?: (evidence: unknown[]) => void,
  onValidation?: (validation: { passed: boolean; diagnostic?: string }) => void,
): Promise<void> {
  const session = readSession()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
  }
  if (session) headers['Authorization'] = `Bearer ${session.token}`

  const streamStartedAt = performance.now()
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/search/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return
    onError('Le service est indisponible. Vérifiez que la plateforme est démarrée.')
    return
  }

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      writeSession(null)
      window.dispatchEvent(new Event('avaliance:session-expired'))
    }
    onError(`Le service a retourné une erreur HTTP ${response.status}.`)
    return
  }

  if (!response.body) {
    onError('Streaming non supporté par le navigateur.')
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let firstChunkMetricSent = false
  let buffer = ''
  let completed = false
  let currentEvent = 'message'
  let currentDataLines: string[] = []
  let streamedCitations: Array<{
    citationId?: string | null; requestId?: string | null;
    chunkId: number; missionId: number | null; missionTitle: string | null;
    documentId: number | null; documentName: string | null; page: number | null;
    corpusScope?: 'PDF' | 'MISSION' | 'LEGACY_SYNTHETIC' | null;
    content: string; score: number; rrfScore?: number | null; relevanceScore?: number | null; sourceIndex?: number;
  }> = []

  const emitMetric = (name: string, valueMs: number) => onMetric?.({ name, valueMs })
  const mergeCitations = (incoming: typeof streamedCitations) => {
    const citationsBySource = new Map(
      streamedCitations.map((citation) => [
        citation.citationId ?? `${citation.chunkId}-${citation.sourceIndex ?? ''}`,
        citation,
      ]),
    )
    for (const citation of incoming) {
      citationsBySource.set(
        citation.citationId ?? `${citation.chunkId}-${citation.sourceIndex ?? ''}`,
        citation,
      )
    }
    streamedCitations = Array.from(citationsBySource.values())
    return streamedCitations
  }

  const processEvent = (eventName: string, dataLines: string[]) => {
    const jsonStr = dataLines.join('\n').trim()
    if (!jsonStr) return

    try {
      const data = JSON.parse(jsonStr)
      if (data.status === 'retrieving' || data.status === 'generating') onStatus?.(data.status)
      if (eventName === 'delta' || data.token) onToken(data.token ?? '')
      if (eventName === 'evidence' && Array.isArray(data.evidence)) onEvidence?.(data.evidence)
      if (eventName === 'validation' && typeof data.passed === 'boolean') {
        onValidation?.({ passed: data.passed, diagnostic: data.diagnostic })
      }
      if ((eventName === 'citation' || eventName === 'citations') && Array.isArray(data.citations)) {
        onCitation?.(mergeCitations(data.citations))
      }
      if (eventName === 'done' || data.done) {
        completed = true
        emitMetric('stream-total', performance.now() - streamStartedAt)
        const finalCitations = Array.isArray(data.citations)
          ? mergeCitations(data.citations)
          : streamedCitations
        onDone(finalCitations, data.confidence ?? 0)
      }
      if (eventName === 'error' || data.error) {
        completed = true
        onError(data.error ?? 'La génération a échoué. Réessayez.')
      }
    } catch {
      // Ignore heartbeats and non-JSON server comments.
    }
  }

  const processLine = (line: string) => {
    const trimmed = line.trimEnd()
    if (!trimmed) {
      processEvent(currentEvent, currentDataLines)
      currentEvent = 'message'
      currentDataLines = []
      return
    }
    if (trimmed.startsWith(':')) return
    if (trimmed.startsWith('event:')) {
      currentEvent = trimmed.slice(6).trim() || 'message'
      return
    }
    if (trimmed.startsWith('data:')) {
      currentDataLines.push(trimmed.slice(5).trim())
      return
    }
    currentDataLines.push(trimmed)
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      if (!firstChunkMetricSent) {
        firstChunkMetricSent = true
        emitMetric('stream-first-byte', performance.now() - streamStartedAt)
      }
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()!

      lines.forEach(processLine)
    }
    buffer += decoder.decode()
    buffer.split('\n').forEach(processLine)
    if (currentDataLines.length > 0) processEvent(currentEvent, currentDataLines)
    if (!completed && !signal?.aborted) onError('La réponse a été interrompue avant sa finalisation. Relancez la recherche.')
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) {
      onError('La connexion au flux de réponse a été interrompue.')
    }
  } finally {
    reader.releaseLock()
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Une erreur inattendue est survenue.'
}