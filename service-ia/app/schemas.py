"""Pydantic v2 schemas for service-ia request/response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CorpusScope = Literal["PDF", "MISSION", "LEGACY_SYNTHETIC"]

# ---------------------------------------------------------------------------
# /embed
# ---------------------------------------------------------------------------
class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, description="Raw texts to encode into BGE-M3 vectors")


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    dimension: int
    count: int


# ---------------------------------------------------------------------------
# /ingest
# ---------------------------------------------------------------------------
class IngestMissionDocument(BaseModel):
    chunk_index: int
    kind: str
    content: str = Field(..., min_length=1)


class IngestMissionRequest(BaseModel):
    id: str
    title: str
    sector: str
    mission_type: str
    technologies: list[str]
    year: int
    referent_tag: str | None = None
    summary: str
    documents: list[IngestMissionDocument] = Field(..., min_length=1)


class IngestRequest(BaseModel):
    missions: list[IngestMissionRequest] = Field(..., min_length=1)
    chunk_max_characters: int = Field(default=512, ge=64)
    chunk_overlap_characters: int = Field(default=64, ge=0)


class IngestResponse(BaseModel):
    missions_inserted: int
    chunks_inserted: int
    chunks_with_embeddings: int


# ---------------------------------------------------------------------------
# /retrieve
# ---------------------------------------------------------------------------
class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    sector: str | None = None
    mission_type: str | None = None
    year: int | None = None
    corpus_scope: CorpusScope = Field(default="PDF")
    request_id: str | None = None


class RetrievedChunk(BaseModel):
    chunk_id: int
    mission_id: int | None = None
    mission_title: str | None = None
    document_id: int | None = None
    document_name: str | None = None
    page: int | None = None
    sector: str | None = None
    mission_type: str | None = None
    corpus_scope: CorpusScope
    request_id: str | None = None
    content: str
    score: float  # Backward-compatible alias for the rank-only RRF score.
    rrf_score: float | None = None
    relevance_score: float | None = None
    vector_score: float | None = None
    text_score: float | None = None


class RetrieveResponse(BaseModel):
    query: str
    chunks: list[RetrievedChunk]
    total_found: int


# ---------------------------------------------------------------------------
# /similar
# ---------------------------------------------------------------------------
class SimilarRequest(BaseModel):
    description: str = Field(..., min_length=1)
    sector: str | None = None
    mission_type: str | None = None
    top_k: int = Field(default=5, ge=1, le=50)


class SimilarMission(BaseModel):
    id: int
    title: str
    sector: str
    mission_type: str
    technologies: list[str]
    year: int
    summary: str
    similarity_score: float


class SimilarResponse(BaseModel):
    missions: list[SimilarMission]


# ---------------------------------------------------------------------------
# /generate
# ---------------------------------------------------------------------------
class GenerateRequest(BaseModel):
    query: str = Field(..., min_length=1)
    request_id: str | None = None
    chunks: list[RetrievedChunk]


class EvidenceItem(BaseModel):
    evidence_id: int = Field(..., ge=1)
    chunk_id: int
    mission_id: int | None = None
    mission_title: str | None = None
    document_id: int | None = None
    document_name: str | None = None
    page: int | None = None
    corpus_scope: CorpusScope
    request_id: str | None = None
    content: str
    source_start: int = Field(..., ge=0)
    source_end: int = Field(..., ge=0)


class Citation(BaseModel):
    citation_id: str
    chunk_id: int
    mission_id: int | None = None
    mission_title: str | None = None
    document_id: int | None = None
    document_name: str | None = None
    page: int | None = None
    corpus_scope: CorpusScope
    request_id: str | None = None
    content: str
    score: float  # Backward-compatible alias for the rank-only RRF score.
    rrf_score: float | None = None
    relevance_score: float | None = None
    source_index: int | None = Field(default=None, ge=1)


class EvidenceSpan(BaseModel):
    """A validated factual claim and its exact source range in selected evidence."""

    evidence_id: int = Field(..., ge=1)
    chunk_id: int
    quote: str = Field(..., min_length=1)
    source_start: int = Field(..., ge=0)
    source_end: int = Field(..., ge=0)
    answer_start: int = Field(..., ge=0)
    answer_end: int = Field(..., ge=0)


class GenerateResponse(BaseModel):
    answer: str
    citations: list[Citation]
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    validation_passed: bool = False
    diagnostic: Literal[
        "NO_RELEVANT_EVIDENCE",
        "UNSUPPORTED_ANSWER",
        "INVALID_CITATION_FORMAT",
    ] | None = None


# ---------------------------------------------------------------------------
# /rfp — isolated proposal workflow. It deliberately does not reuse /search.
# ---------------------------------------------------------------------------
ClaimKind = Literal[
    "brief_fact",
    "internal_evidence",
    "web_evidence",
    "recommendation",
    "assumption",
    "question",
]

SectionStatus = Literal[
    "complete",
    "tailored",
    "not_applicable",
    "requires_clarification",
]


class RfpAtomicNeed(BaseModel):
    id: str
    text: str
    category: str = "general"
    source_excerpt: str | None = None


class RfpRequirements(BaseModel):
    sector: str | None = None
    organization_type: str | None = None
    business_problem: list[str] = Field(default_factory=list)
    project_type: list[str] = Field(default_factory=list)
    technologies_and_constraints: list[str] = Field(default_factory=list)
    security_and_compliance: list[str] = Field(default_factory=list)
    expected_deliverables: list[str] = Field(default_factory=list)
    scale: list[str] = Field(default_factory=list)
    timeline_and_urgency: list[str] = Field(default_factory=list)
    budget: str | None = None
    criteria: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    ambiguities_and_questions: list[str] = Field(default_factory=list)
    atomic_needs: list[RfpAtomicNeed] = Field(default_factory=list)


class RfpScoreBreakdown(BaseModel):
    sector_match: float = Field(ge=0.0, le=1.0)
    project_type_match: float = Field(ge=0.0, le=1.0)
    business_need_match: float = Field(ge=0.0, le=1.0)
    constraint_match: float = Field(ge=0.0, le=1.0)
    technology_match: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)


class RfpComparableMission(SimilarMission):
    score_breakdown: RfpScoreBreakdown


class RfpCitation(BaseModel):
    citation_id: str
    chunk_id: int
    document_id: int
    document_name: str
    page: int
    content: str
    source_index: int = Field(ge=1)


class RfpSource(BaseModel):
    id: str
    type: Literal["brief", "internal_pdf", "web"]
    title: str
    document_id: int | None = None
    document_name: str | None = None
    page: int | None = None
    chunk_id: int | None = None
    excerpt: str | None = None
    url: str | None = None
    publisher: str | None = None
    score: float | None = None


class RfpTable(BaseModel):
    title: str
    columns: list[str] = Field(min_length=1)
    rows: list[list[str]] = Field(default_factory=list)


class RfpClaim(BaseModel):
    """A proposal statement with explicit provenance."""

    id: str | None = None
    text: str = Field(min_length=1)
    kind: ClaimKind = "recommendation"
    source_ids: list[str] = Field(default_factory=list)
    citation_indexes: list[int] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class RfpSection(BaseModel):
    key: str
    order: int = 1
    title: str
    status: SectionStatus = "complete"
    status_reason: str | None = None
    summary: str | None = None
    narrative: list[str] = Field(default_factory=list)
    claims: list[RfpClaim] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)
    tables: list[RfpTable] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    facts_from_brief: list[str] = Field(default_factory=list)
    verified_references: list[RfpClaim] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    assumptions_to_confirm: list[str] = Field(default_factory=list)


class RfpProposal(BaseModel):
    title: str = "Proposition de réponse"
    executive_summary: str | None = None
    sections: list[RfpSection] = Field(min_length=1)
    legacy_markdown: str | None = None


class RfpCoverageItem(BaseModel):
    need_id: str
    covered: bool = True
    section_keys: list[str] = Field(default_factory=list)


class RfpQualityReport(BaseModel):
    passed: bool = True
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    coverage_score: float = Field(default=1.0, ge=0.0, le=1.0)
    citation_integrity: float | None = None
    section_count: int = 19
    warnings: list[str] = Field(default_factory=list)


class RfpRequest(BaseModel):
    description: str = Field(..., min_length=1)
    sector: str | None = None
    mission_type: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    request_id: str | None = None
    web_research_enabled: bool = False


class RfpResponse(BaseModel):
    request_id: str | None = None
    requirements: RfpRequirements
    proposal: RfpProposal
    sources: list[RfpSource] = Field(default_factory=list)
    citations: list[RfpCitation] = Field(default_factory=list)
    coverage_report: list[RfpCoverageItem] = Field(default_factory=list)
    similar_missions: list[RfpComparableMission] = Field(default_factory=list)
    evidence_validation_passed: bool
    quality: RfpQualityReport | None = None
    diagnostic: str | None = None
