import type { ApiErrorBody, AuthSession, DashboardSummary, Mission, MissionPage, RegisterUserRequest, RfpResponse, SearchRequest, SearchResponse, SourceDocument, SourceDocumentPage, UserAccount } from '../types.ts'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'
const SESSION_KEY = 'avaliance-copilot-session'
const AUTH_REQUEST_TIMEOUT_MS = 15_000
// Proposal generation includes PDF retrieval and grounded drafting; it must never
// inherit the deliberately short authentication timeout.
const RFP_REQUEST_TIMEOUT_MS = 180_000

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
  const legacyStructure = root && typeof (root.rfpStructure ?? root.rfp_structure) === 'string'
    ? (root.rfpStructure ?? root.rfp_structure) as string
    : null
  if (!root || (!proposal || !sections) && !legacyStructure) {
    throw new ApiError('La réponse de proposition est invalide ou incomplète. Réessayez.', 502)
  }
  const safeSections = sections ?? []

  return {
    requirements: (asRecord(root.requirements) ?? {}) as unknown as RfpResponse['requirements'],
    proposal: {
      title: typeof proposal?.title === 'string' ? proposal.title : 'Proposition de réponse',
      legacyMarkdown: legacyStructure ?? undefined,
      sections: safeSections.map((value, index) => {
        const section = asRecord(value)
        if (!section || typeof section.title !== 'string') throw new ApiError(`La section ${index + 1} de la proposition est invalide. Réessayez.`, 502)
        const rawBlocks: unknown[] = Array.isArray(section.blocks) ? section.blocks : []
        const blocks: RfpResponse['proposal']['sections'][number]['blocks'] = rawBlocks.flatMap((value) => {
          const block = asRecord(value)
          const kind = block?.kind
          const rawTable = asRecord(block?.table)
          const rows: unknown[] = Array.isArray(rawTable?.rows) ? rawTable.rows : []
          const table = rawTable && typeof rawTable.title === 'string'
            ? { title: rawTable.title, columns: strings(rawTable.columns), rows: rows.map(strings) }
            : undefined
          return block && (kind === 'paragraph' || kind === 'bullets' || kind === 'table' || kind === 'callout')
            ? [{ kind, text: typeof block.text === 'string' ? block.text : undefined, items: strings(block.items), table, evidenceIds: strings(block.evidenceIds ?? block.evidence_ids) }]
            : []
        })
        if (blocks.length === 0 && !legacyStructure) throw new ApiError(`La section ${index + 1} ne contient aucun bloc lisible. Réessayez.`, 502)
        return { id: typeof section.id === 'string' ? section.id : typeof section.key === 'string' ? section.key : `section-${index + 1}`, title: section.title, level: typeof section.level === 'number' ? section.level : 2, blocks }
      }),
    },
    evidence: Array.isArray(root.evidence) ? root.evidence.flatMap((value) => {
      const evidence = asRecord(value)
      const id = evidence?.id
      const documentId = evidence?.documentId ?? evidence?.document_id
      const missionId = evidence?.missionId ?? evidence?.mission_id
      return typeof id === 'string' && typeof documentId === 'number' && typeof evidence?.page === 'number' && typeof evidence.quote === 'string' && evidence.quote.trim()
        ? [{ id, documentId, missionId: typeof missionId === 'number' ? missionId : null, page: evidence.page, quote: evidence.quote }]
        : []
    }) : [],
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
                sectorMatch: score('sectorMatch') ?? score('sector_match') ?? finalScore,
                projectTypeMatch: score('projectTypeMatch') ?? score('project_type_match') ?? finalScore,
                businessNeedMatch: score('businessNeedMatch') ?? score('business_need_match') ?? finalScore,
                constraintMatch: score('constraintMatch') ?? score('constraint_match') ?? finalScore,
                technologyMatch: score('technologyMatch') ?? score('technology_match') ?? finalScore,
                finalScore,
              },
            }] : []
      })
    })(),
    evidenceValidationPassed: root.evidenceValidationPassed === true || root.evidence_validation_passed === true,
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
      const body = await response.json().catch(() => ({})) as ApiErrorBody
      const fallback = response.status === 401
        ? 'Identifiant ou mot de passe incorrect.'
        : response.status === 403
          ? 'Accès refusé. Vérifiez l’adresse du frontend et les origines CORS autorisées.'
          : `Le service a retourné une erreur HTTP ${response.status}.`
      throw new ApiError(body.message ?? body.error ?? fallback, response.status)
    }
    if (response.status === 204) return undefined as T
    return await response.json() as T
  } catch (error) {
    if (timeoutController?.signal.aborted) {
      throw new ApiError('Erreur de connexion : le serveur est injoignable ou la demande a expiré. Réessayez.', 0)
    }
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('Erreur de connexion : la demande a été annulée.', 0)
    }
    // Browsers intentionally hide CORS details from fetch; a TypeError therefore
    // represents the same actionable condition as a refused network connection.
    throw new ApiError('Erreur de connexion : le serveur est injoignable. Vérifiez que la plateforme est démarrée et que l’origine du frontend est autorisée.', 0)
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
  generateRfp: async (payload: { description: string; sector?: string; missionType?: string; topK?: number }) => {
    const response = await request<unknown>('/rfp/generate', {
      method: 'POST',
      body: JSON.stringify({ description: payload.description, sector: payload.sector, missionType: payload.missionType, topK: payload.topK }),
    }, RFP_REQUEST_TIMEOUT_MS)
    return parseRfpResponse(response)
  },
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