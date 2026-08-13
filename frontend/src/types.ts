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

export interface RfpTable {
  title: string
  columns: string[]
  rows: string[][]
}

export interface RfpClaim {
  text: string
  citationIndexes: number[]
}

export interface RfpSection {
  key: string
  title: string
  factsFromBrief: string[]
  verifiedReferences: RfpClaim[]
  recommendations: string[]
  assumptionsToConfirm: string[]
  tables: RfpTable[]
}

export interface RfpProposal {
  title: string
  sections: RfpSection[]
  /** Compatibility content from the retired RFP contract. Never treat it as a brief fact. */
  legacyMarkdown?: string
}

export interface RfpResponse {
  requirements: Record<string, string | string[] | null>
  proposal: RfpProposal
  citations: RfpCitation[]
  similarMissions: RfpComparableMission[]
  evidenceValidationPassed: boolean
  diagnostic: string | null
}

export interface ApiErrorBody {
  message?: string
  error?: string
}