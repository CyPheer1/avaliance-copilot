export type UserRole = 'ADMIN' | 'CONSULTANT'

export interface AuthSession {
  token: string
  username: string
  role: UserRole
}

export interface UserAccount {
  id: number
  username: string
  role: UserRole
}

export interface RegisterUserRequest {
  username: string
  password: string
  role: UserRole
}

export interface DashboardBreakdown {
  label: string
  total: number
}

export interface DashboardSummary {
  generatedAt: string
  periodDays: number
  missionTotal: number
  missionsBySector: DashboardBreakdown[]
  missionsByType: DashboardBreakdown[]
  missionsByYear: Array<{ year: number; total: number }>
  userTotal: number
  adminCount: number
  consultantCount: number
  activity: {
    total: number
    searches: number
    similarities: number
    rfpGenerations: number
    successes: number
    errors: number
    successRate: number
    averageDurationMs: number
  }
  dailyActivity: Array<{ day: string; total: number; errors: number }>
  recentActivity: Array<{ action: string; status: string; durationMs: number | null; createdAt: string }>
}

export interface Mission {
  id: number
  title: string
  sector: string
  missionType: string
  technologies: string[]
  year: number
  referentTag: string | null
  summary: string
  createdAt: string
}

export interface MissionPage {
  content: Mission[]
  totalPages: number
  totalElements: number
  size: number
  number: number
  numberOfElements: number
  first: boolean
  last: boolean
  empty: boolean
}

export interface SearchRequest {
  query: string
  sector?: string
  missionType?: string
  year?: number
  topK: number
}

export interface Citation {
  citationId?: string | null
  requestId?: string | null
  chunkId: number
  missionId: number | null
  missionTitle: string | null
  documentId: number | null
  documentName: string | null
  page: number | null
  corpusScope?: 'PDF' | 'MISSION' | 'LEGACY_SYNTHETIC' | null
  content: string
  score: number
  rrfScore?: number | null
  relevanceScore?: number | null
  sourceIndex?: number
}

export interface SearchResponse {
  answer: string
  citations: Citation[]
  confidence: number
}

export type DocumentStatus = 'STORED' | 'PROCESSING' | 'INDEXED' | 'FAILED'

export interface SourceDocument {
  id: number
  filename: string
  mediaType: string
  sizeBytes: number
  sha256: string
  status: DocumentStatus
  uploadedBy: string
  pageCount: number | null
  chunkCount: number | null
  errorMessage: string | null
  createdAt: string
  indexedAt: string | null
}

export interface SourceDocumentPage {
  content: SourceDocument[]
  totalPages: number
  totalElements: number
  size: number
  number: number
  numberOfElements: number
  first: boolean
  last: boolean
  empty: boolean
}

export interface SimilarMission {
  id: number
  title: string
  sector: string
  missionType?: string
  mission_type?: string
  technologies: string[]
  year: number
  summary: string
  similarityScore?: number
  similarity_score?: number
}

export interface RfpScoreBreakdown {
  sectorMatch: number
  projectTypeMatch: number
  businessNeedMatch: number
  constraintMatch: number
  technologyMatch: number
  finalScore: number
}

export interface RfpComparableMission extends SimilarMission {
  scoreBreakdown: RfpScoreBreakdown
}

export interface RfpCitation extends Citation {
  citationId: string
  documentId: number
  documentName: string
  page: number
  sourceIndex: number
}

export type ClaimKind =
  | 'brief_fact'
  | 'internal_evidence'
  | 'web_evidence'
  | 'recommendation'
  | 'assumption'
  | 'question'

export type SectionStatus =
  | 'complete'
  | 'tailored'
  | 'not_applicable'
  | 'requires_clarification'

export interface RfpSource {
  id: string
  type: 'brief' | 'internal_pdf' | 'web'
  title: string
  documentId?: number
  documentName?: string
  page?: number
  chunkId?: number
  excerpt?: string
  url?: string
  publisher?: string
  score?: number
}

export interface RfpTable {
  title: string
  columns: string[]
  rows: string[][]
}

export interface RfpClaim {
  id?: string
  text: string
  kind?: ClaimKind
  sourceIds?: string[]
  citationIndexes: number[]
  confidence?: number
}

export interface RfpBulletAnchor {
  type: 'fact' | 'requirement' | 'assumption' | 'recommendation'
  id?: string | null
}

export interface RfpBullet {
  text: string
  anchor?: RfpBulletAnchor | null
}

export interface RfpSectionEvidence {
  id: string
  source_document_id: number
  page?: number | null
  chunk_id: number
  quote?: string | null
}

export interface EvidencePacket {
  requirement_id: string
  status: 'SUPPORTED' | 'NO_RELEVANT_EVIDENCE'
  evidence: RfpSectionEvidence[]
}

export interface RfpSection {
  key: string
  order?: number
  title: string
  status?: SectionStatus
  statusReason?: string
  summary?: string
  body?: string | null
  narrative?: string[]
  claims?: RfpClaim[]
  bullets?: RfpBullet[]
  tables: RfpTable[]
  questions?: string[]
  factsFromBrief: string[]
  verifiedReferences: RfpClaim[]
  recommendations: string[]
  assumptions: string[]
  assumptionsToConfirm: string[]
  evidence: RfpSectionEvidence[]
}

export interface RfpProposal {
  title: string
  executiveSummary?: string
  sections: RfpSection[]
  /** Compatibility content from the retired RFP contract. Never treat it as a brief fact. */
  legacyMarkdown?: string
}

export interface RfpClusterMetric {
  clusterKeys: string[]
  mode: 'llm' | 'deterministic_fallback'
  durationMs: number
  warningCode?: string | null
}

export interface RfpQualityReport {
  passed: boolean
  score?: number | null
  coverageScore?: number | null
  citationIntegrity?: number | null
  sectionCount?: number | null
  generationMode?: 'llm' | 'mixed_fallback' | 'deterministic_fallback' | 'repair_failed' | null
  plannerMode?: 'llm' | 'deterministic_fallback' | null
  extractionMode?: 'llm' | 'deterministic_fallback' | null
  repairAttempted?: boolean
  failedClusterKeys?: string[]
  coverageDetail?: number | null
  provenanceDetail?: number | null
  specificityDetail?: number | null
  solutionQualityDetail?: number | null
  governanceDetail?: number | null
  writingDetail?: number | null
  sourceQualityDetail?: number | null
  warnings: string[]
}

export interface ComplianceMatrixRow {
  requirement_id: string
  covered: boolean
  section_keys: string[]
}

export interface SourceRegisterEntry {
  id: string
  document_id: number
  title: string
  pages: number[]
}

export interface RfpAnnexes {
  compliance_matrix: ComplianceMatrixRow[]
  source_register: SourceRegisterEntry[]
}

export interface RfpMetrics {
  call_a_ms: number
  retrieval_ms: number
  planning_ms: number
  call_b_ms: number
  call_c_ms: number
  validation_ms: number
  repair_ms: number
  total_ms: number
  word_count: number
  section_count: number
  fallback_used: boolean
}

export interface RfpJob {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  progressStep?: string
  requestId?: string
  errorCode?: string
  errorMessageSafe?: string
}

export interface RfpResponse {
  requestId?: string
  mode: 'brief' | 'standard' | 'full'
  status: 'completed' | 'failed' | 'pending'
  requirements: Record<string, string | string[] | null>
  proposal: RfpProposal
  annexes?: RfpAnnexes
  metrics?: RfpMetrics
  sources?: RfpSource[]
  citations: RfpCitation[]
  coverageReport?: Array<{ needId: string; covered: boolean; sectionKeys: string[] }>
  clusterMetrics?: RfpClusterMetric[]
  similarMissions: RfpComparableMission[]
  evidenceValidationPassed: boolean
  quality?: RfpQualityReport
  diagnostic: string | null
}

export interface ApiErrorBody {
  message?: string
  error?: string
}