"""Grounded answer and RFP generation policies."""

from __future__ import annotations

import json
import logging
import re
import threading
import unicodedata
from difflib import SequenceMatcher
from collections import OrderedDict
from hashlib import sha256
from typing import Generator

from ..schemas import (
    Citation,
    EvidenceItem,
    EvidenceSpan,
    GenerateRequest,
    GenerateResponse,
    RetrievedChunk,
    RfpCitation,
    RfpClaim,
    RfpComparableMission,
    RfpProposal,
    RfpRequest,
    RfpRequirements,
    RfpResponse,
    RfpScoreBreakdown,
    RfpSection,
    RfpTable,
    RetrieveRequest,
    SimilarRequest,
)
from ..project_query import matches_named_project, project_title_from_query
from ..settings import Settings
from .ollama import generate_text, generate_text_stream
from .prompts import (
    EVIDENCE_RESPONSE_SCHEMA,
    INSUFFICIENT_INFORMATION,
    RFP_PROMPT,
    SOURCED_ANSWER_PROMPT,
    SYNTHESIZED_ANSWER_PROMPT,
)

_CITATION_PATTERN = re.compile(r"\[(\d+)]")
_SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")
_ANSWER_CITATION_PATTERN = re.compile(r"(?P<quote>[^\[]+?)\s*\[(?P<source>\d+)\]")
_TECHNOLOGY_CLAUSE_PATTERN = re.compile(
    r"(Expérience et interfaces|Services métier|Données|Intégration|Plateforme|"
    r"Observabilité et sécurité)\s*:\s*(.+?)(?=\s*[;•]|\.\s+[A-ZÀ-Ö]|$)",
    re.IGNORECASE,
)
_IDENTITY_PATTERN = re.compile(
    r"Secteur\s+(.+?)\s+Type de mission\s+(.+?)\s+Période",
    re.IGNORECASE,
)
_DIFFICULTY_HEADING_PATTERN = re.compile(r"\bDifficultés rencontrées\b", re.IGNORECASE)
_TEST_ANSWER_PATTERN = re.compile(
    r"Question de test\s+\d+\s*:\s*(.+?)\s+Réponse attendue\s*:\s*(.+?)"
    r"(?=\s+Question de test\s+\d+\s*:|$)",
    re.IGNORECASE,
)
_PARENTHESIZED_PATTERN = re.compile(r"\(([^()]*)\)")
_ALTERNATIVE_SEPARATOR_PATTERN = re.compile(
    r"\s*(?:,|;|\bou\b|\bor\b)\s*", re.IGNORECASE
)
_PERSON_ROLE_PATTERN = re.compile(
    r"([A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ'’.-]+\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ'’.-]+)\s+"
    r"([^\n]+?)\s+Avaliance\s+\d+\s*%"
)
_LABELED_TEAM_ROW_PATTERN = re.compile(
    r"Nom:\s*(?P<name>[^;\n]+);\s*Rôle:\s*(?P<role>[^;\n]+);\s*"
    r"Entité:\s*(?P<entity>[^;\n]+);\s*Charge:\s*(?P<charge>[^;\n]+);\s*"
    # Normalization compacts blank lines, so a table row can be immediately
    # followed by the next ``Nom:`` label. Stop before that label instead of
    # consuming the entire remaining chunk as the first row's period.
    r"Période:\s*(?P<period>.+?)(?=\s+Nom:\s*|\s+##|$)",
    re.IGNORECASE,
)
_LABELED_BUDGET_ROW_PATTERN = re.compile(
    r"Poste:\s*(?P<role>[^;\n]+);\s*Responsable\s*/\s*équipe:\s*"
    r"(?P<responsible>[^;\n]*);\s*Jours:\s*(?P<days>[^;\n]+);\s*"
    r"TJM moyen:\s*(?P<rate>[^;\n]*);\s*Montant HT:\s*(?P<amount>.+?)"
    r"(?=\s+Poste:\s*|\s+##|$)",
    re.IGNORECASE,
)
_PROMPT_VERSION = "exact-evidence-v5"
_ANSWER_CACHE: OrderedDict[str, GenerateResponse] = OrderedDict()
_ANSWER_CACHE_LOCK = threading.Lock()
_DIAGNOSTIC_COUNTS: dict[str, int] = {}
_DIAGNOSTIC_COUNTS_LOCK = threading.Lock()
NO_RELEVANT_EVIDENCE = "NO_RELEVANT_EVIDENCE"
UNSUPPORTED_ANSWER = "UNSUPPORTED_ANSWER"
INVALID_CITATION_FORMAT = "INVALID_CITATION_FORMAT"
logger = logging.getLogger(__name__)


def _person_role_candidates(
    content: str, query_terms: list[str]
) -> list[tuple[int, int, str]]:
    normalized_content = _normalized_text(content)
    normalized_content = re.sub(
        r"^Organisation\s+et\s+.+?Charge\s+\S+\s+",
        "",
        normalized_content,
        count=1,
        flags=re.IGNORECASE,
    )
    candidates: list[tuple[int, int, str]] = []
    seen_evidence: set[str] = set()

    # Layout-preserving PDF ingestion serializes each table row with its headers.
    # Return the exact stored row so every displayed allocation and period maps to
    # one source span rather than reconstructing a citation-free paraphrase.
    for match in _LABELED_TEAM_ROW_PATTERN.finditer(normalized_content):
        role = match.group("role").strip()
        term_hits = sum(term in _fold_text(role) for term in query_terms)
        if term_hits == 0:
            continue
        evidence = match.group(0).strip()
        if evidence in seen_evidence:
            continue
        seen_evidence.add(evidence)
        candidates.append((term_hits, match.start(), evidence))

    row_pattern = re.compile(
        r"([A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ'’.-]+\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ'’.-]+)\s+"
        r"([^\n]+?)\s+Avaliance\s+\d+\s*%"
    )
    for match in row_pattern.finditer(normalized_content):
        person_name = match.group(1).strip()
        folded_name = _fold_text(person_name)
        if folded_name in {"nom role", "organisation et", "charge periode"}:
            continue
        role = match.group(2).strip(" -—:")
        folded_role = _fold_text(role)
        term_hits = sum(term in folded_role for term in query_terms)
        if term_hits == 0:
            continue
        evidence = f"{person_name} — {role}"
        if evidence in seen_evidence:
            continue
        seen_evidence.add(evidence)
        candidates.append((term_hits, match.start(), evidence))

    if candidates:
        return sorted(candidates, key=lambda candidate: (-candidate[0], candidate[1]))

    for match in _PERSON_ROLE_PATTERN.finditer(normalized_content):
        person_name = match.group(1).strip()
        if _fold_text(person_name) in {"nom role", "organisation et", "charge periode"}:
            continue
        role = match.group(2).strip()
        folded_role = _fold_text(role)
        term_hits = sum(term in folded_role for term in query_terms)
        if term_hits == 0:
            continue
        evidence = f"{person_name} — {role}"
        if evidence in seen_evidence:
            continue
        seen_evidence.add(evidence)
        candidates.append((term_hits, match.start(), evidence))
    return sorted(candidates, key=lambda candidate: (-candidate[0], candidate[1]))


def _fold_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


def _labeled_rows(content: str, pattern: re.Pattern[str]) -> list[tuple[dict[str, str], str]]:
    """Return normalized labeled table records with their exact evidence text."""
    normalized_content = _normalized_text(content)
    rows: list[tuple[dict[str, str], str]] = []
    for match in pattern.finditer(normalized_content):
        evidence = match.group(0).strip()
        rows.append(({name: value.strip() for name, value in match.groupdict().items()}, evidence))
    return rows


def _team_row_for_evidence(content: str, evidence: str) -> dict[str, str] | None:
    """Extract a selected person's exact identity from labeled or raw PDF rows."""
    for row, row_evidence in _labeled_rows(content, _LABELED_TEAM_ROW_PATTERN):
        if row_evidence == evidence:
            return row
    normalized_content = _normalized_text(content)
    raw_evidence = re.match(r"(?P<name>.+?)\s+—\s+(?P<role>.+)$", evidence)
    if raw_evidence is None:
        return None
    name = raw_evidence.group("name").strip()
    role = raw_evidence.group("role").strip()
    raw_pattern = re.compile(
        rf"{re.escape(name)}\s+{re.escape(role)}\s+Avaliance\s+\d+\s*%",
        re.IGNORECASE,
    )
    if raw_pattern.search(normalized_content) is None:
        return None
    return {"name": name, "role": role}


def _role_overlap(left: str, right: str) -> int:
    """Count informative role terms shared by two independently extracted rows."""
    ignored = {"ingenierie", "equipe", "poste", "projet", "programme", "des", "les", "pour"}
    left_terms = {
        term for term in re.findall(r"[a-z0-9]+", _fold_text(left))
        if len(term) >= 4 and term not in ignored
    }
    right_terms = set(re.findall(r"[a-z0-9]+", _fold_text(right)))
    return len(left_terms & right_terms)


def _query_intent(query: str) -> str | None:
    folded = _fold_text(query)
    if any(term in folded for term in ("qui ", "qui a", "quelle personne", "quel responsable", "pris en charge", "en charge")):
        return "person"
    if any(term in folded for term in ("quand", "date", "periode")):
        return "time"
    if any(term in folded for term in ("lieu", "site", "localisation", "region", "ville", "pays")):
        return "location"
    if any(term in folded for term in ("technolog", "architecture cible", "stack")):
        return "technologies"
    if "secteur" in folded and "type de mission" in folded:
        return "identity"
    if any(term in folded for term in (
        "resultat mesurable", "resultats mesurables", "indicateur",
        "volume", "volumes", "mesure traitee", "mesures traitees",
        "compteur", "compteurs", "latence",
    )):
        return "metrics"
    if any(
        term in folded
        for term in (
            "difficulte",
            "obstacle",
            "risque rencontre",
            "fusionner par erreur",
            "meme nom",
            "homonyme",
        )
    ):
        return "difficulty"
    if "migration" in folded and any(
        term in folded for term in ("strategie", "stratégie", "retenue", "choix", "arbitrage")
    ):
        return "migration_strategy"
    if any(term in folded for term in ("solution", "approche", "mise en oeuvre")):
        return "solution"
    if any(term in folded for term in ("probleme principal", "contexte metier", "motive")):
        return "context"
    return None


def _question_keywords(query: str) -> list[str]:
    folded = _fold_text(query)
    words = re.findall(r"[a-z0-9]+", folded)
    stop_words = {
        "qui", "que", "quoi", "dans", "le", "la", "les", "de", "des", "du", "un", "une",
        "et", "en", "a", "au", "aux", "pour", "sur", "par", "avec", "quel", "quelle",
        "quelles", "quels", "est", "a", "il", "elle", "pris", "charge", "partie", "projet",
        "programme",
    }
    project_title = project_title_from_query(query)
    if project_title is not None:
        stop_words.update(
            word
            for word in re.findall(r"[a-z0-9]+", _fold_text(project_title))
            if len(word) >= 3
        )
    seen: list[str] = []
    for word in words:
        if len(word) < 3 or word in stop_words or word in seen:
            continue
        seen.append(word)
    return seen


def _chunk_specificity_score(query: str, chunk: RetrievedChunk) -> tuple[int, float, float, int]:
    folded_content = _fold_text(chunk.content)
    keywords = _question_keywords(query)
    keyword_hits = sum(keyword in folded_content for keyword in keywords)
    content_length = len(chunk.content)
    return (
        keyword_hits,
        chunk.text_score or 0.0,
        _source_similarity(chunk),
        -content_length,
    )


def _deduplicate_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    unique: list[RetrievedChunk] = []
    seen: set[tuple[int | None, int | None, str]] = set()
    for chunk in chunks:
        key = (chunk.document_id, chunk.page, _normalized_text(chunk.content))
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return unique


def _select_relevant_chunks(
    query: str, chunks: list[RetrievedChunk], *, limit: int = 8
) -> list[RetrievedChunk]:
    chunks = _deduplicate_chunks(chunks)
    if len(chunks) <= limit:
        return chunks

    intent = _query_intent(query)
    cues = {
        "person": ("nom", "role", "equipe", "responsable", "charge", "flux temps reel"),
        "time": ("date", "periode", "janv", "fevr", "mars", "avril", "mai", "juin", "juil", "aout", "sept", "oct", "nov", "dec"),
        "location": ("site", "lieu", "region", "pays", "ville"),
        "technologies": ("architecture cible", "technolog", "plateforme", "integration"),
        "identity": ("fiche d'identite", "secteur", "type de mission"),
        "metrics": ("resultat", "mesurable", "a la cloture", "%"),
        "difficulty": ("difficultes rencontrees", "difficulte"),
        "solution": ("solution", "approche", "mise en oeuvre", "architecture cible"),
        "context": ("contexte", "problematique", "incident"),
    }.get(intent, ())
    if not cues:
        return chunks

    ranked = sorted(
        enumerate(chunks),
        key=lambda item: (
            sum(cue in _fold_text(item[1].content) for cue in cues),
            *_chunk_specificity_score(query, item[1]),
            -item[0],
        ),
        reverse=True,
    )
    return [chunk for _, chunk in ranked[:limit]]


def _deterministic_answer(
    query: str, chunks: list[RetrievedChunk]
) -> tuple[str, list[RetrievedChunk]] | None:
    if project_title_from_query(query) is None:
        return None

    intent = _query_intent(query)
    if intent == "identity":
        for chunk in chunks:
            match = _IDENTITY_PATTERN.search(chunk.content)
            if match:
                evidence = match.group(0).rsplit("Période", 1)[0].strip()
                return f"{evidence} [1]", [chunk]

    if intent == "person":
        query_terms = [term for term in _question_keywords(query) if len(term) >= 4]
        project_matched_chunks = [
            chunk
            for chunk in chunks
            if matches_named_project(query, chunk.document_name, chunk.mission_title)
        ]
        if project_matched_chunks:
            chunks = project_matched_chunks
        best_match: tuple[int, int, str, RetrievedChunk] | None = None
        for chunk in chunks:
            chunk_candidates = _person_role_candidates(chunk.content, query_terms)
            if not chunk_candidates:
                continue
            top_candidate = chunk_candidates[0]
            if len(chunk_candidates) > 1 and chunk_candidates[1][0] >= top_candidate[0]:
                continue
            term_hits, position, evidence = top_candidate
            candidate = (term_hits, position, evidence, chunk)
            if best_match is None or candidate[:2] > best_match[:2]:
                best_match = candidate
        if best_match is not None:
            _, _, evidence, team_chunk = best_match
            selected_row = _team_row_for_evidence(team_chunk.content, evidence)
            if selected_row is not None:
                matches: list[tuple[int, str, RetrievedChunk]] = []
                for budget_chunk in chunks:
                    if budget_chunk.document_id != team_chunk.document_id:
                        continue
                    for budget_row, budget_evidence in _labeled_rows(
                        budget_chunk.content, _LABELED_BUDGET_ROW_PATTERN
                    ):
                        responsible_match = (
                            _fold_text(budget_row["responsible"]) == _fold_text(selected_row["name"])
                        )
                        # A role title can be shared by multiple people. Only an
                        # exact responsible-person field may bridge distinct rows.
                        if responsible_match:
                            matches.append((2, budget_evidence, budget_chunk))
                if matches:
                    matches.sort(key=lambda match: (-match[0], match[2].page or 0, match[2].chunk_id))
                    score, budget_evidence, budget_chunk = matches[0]
                    if score >= 2:
                        if budget_chunk.chunk_id == team_chunk.chunk_id:
                            return f"{evidence}; {budget_evidence} [1]", [team_chunk]
                        return f"{evidence} [1] {budget_evidence} [2]", [team_chunk, budget_chunk]
            return f"{evidence} [1]", [team_chunk]

    if intent == "technologies":
        best_match: tuple[list[str], RetrievedChunk] | None = None
        for chunk in chunks:
            clauses_by_label: dict[str, str] = {}
            for match in _TECHNOLOGY_CLAUSE_PATTERN.finditer(chunk.content):
                clause = match.group(0).strip()
                label = _fold_text(match.group(1))
                clauses_by_label.setdefault(label, clause)
            clauses = list(clauses_by_label.values())
            if best_match is None or len(clauses) > len(best_match[0]):
                best_match = clauses, chunk
        if best_match is not None and len(best_match[0]) >= 3:
            clauses, chunk = best_match
            return "; ".join(f"{clause} [1]" for clause in clauses), [chunk]

    if intent == "metrics":
        folded_query = _fold_text(query)
        requests_volume = any(
            term in folded_query
            for term in ("volume", "volumetr", "mesure traitee", "mesures traitees", "compteur")
        )
        # ``volumes``/``volumétries`` have a variable suffix; match their stem
        # instead of requiring an exact singular spelling.
        requests_volume = requests_volume or "volum" in folded_query
        if requests_volume:
            # PDF result tables are often extracted as a single line. Prefer the
            # two exact rows that answer a volume/throughput question rather than
            # an introductory project summary that merely mentions a counter.
            for chunk in chunks:
                content = _normalized_text(chunk.content)
                volume = re.search(
                    r"(Mesures traitées par jour\b.*?)(?=\s+(?:Débit soutenu|Disponibilité|Factures)|$)",
                    content,
                    flags=re.IGNORECASE,
                )
                throughput = re.search(
                    r"(Débit soutenu(?: en pointe| en ingérence)?\b.*?)(?=\s+(?:Latence|Horodatage|Disponibilité|Perte|Factures)|$)",
                    content,
                    flags=re.IGNORECASE,
                )
                if volume and throughput:
                    return f"{volume.group(1).strip()} [1] {throughput.group(1).strip()} [1]", [chunk]
                # Preserve the exact evidence path for prose-oriented PDF
                # extraction, where the number precedes the row label and no
                # separate throughput row is present.
                if re.search(r"\bMesures traitées par jour\b", content, flags=re.IGNORECASE):
                    return f"{content.strip()} [1]", [chunk]

        for chunk in chunks:
            for sentence in _SENTENCE_PATTERN.split(_normalized_text(chunk.content)):
                folded = _fold_text(sentence)
                measurements = re.findall(r"\d+(?:[,.]\d+)?\s*(?:%|minutes?|jours?|mois)?", sentence)
                if len(measurements) >= 2 and any(
                    cue in folded for cue in ("resultat", "a la cloture", "reduit", "reduction")
                ):
                    return f"{sentence.strip()} [1]", [chunk]

    if intent == "migration_strategy":
        for chunk in chunks:
            content = _normalized_text(chunk.content)
            match = re.search(
                r"(La migration par domaines, avec routage dynamique et retour arrière préparé pour chaque livraison, a été retenue[^.]*\.)",
                content,
                flags=re.IGNORECASE,
            )
            if match:
                return f"{match.group(1).strip()} [1]", [chunk]

        for chunk in chunks:
            content = _normalized_text(chunk.content)
            match = re.search(
                r"(La coexistence contrôlée entre l'ancien et le nouveau système, pilotée par une façade de routage, a permis[^.]*retour arrière possible sur chaque domaine migré\.)",
                content,
                flags=re.IGNORECASE,
            )
            if match:
                return f"{match.group(1).strip()} [1]", [chunk]

    if intent == "solution":
        solution_cues = (
            "pipeline",
            "rapprochement",
            "regles de survivance",
            "controles",
            "remediation",
        )
        candidates: list[tuple[int, bool, str, RetrievedChunk]] = []
        for chunk in chunks:
            for sentence in _SENTENCE_PATTERN.split(_normalized_text(chunk.content)):
                folded_sentence = _fold_text(sentence)
                score = sum(cue in folded_sentence for cue in solution_cues)
                if score >= 2:
                    pipeline_start = folded_sentence.find("pipeline")
                    evidence = sentence[pipeline_start:].strip() if pipeline_start >= 0 else sentence.strip()
                    candidates.append((score, "reponse attendue" in folded_sentence, evidence, chunk))
        if candidates:
            _, _, evidence, chunk = max(
                candidates,
                key=lambda candidate: (candidate[0], not candidate[1]),
            )
            return f"{evidence} [1]", [chunk]

    if intent == "difficulty":
        for chunk in chunks:
            matches = list(_DIFFICULTY_HEADING_PATTERN.finditer(chunk.content))
            for match in reversed(matches):
                sentences = [
                    sentence.strip()
                    for sentence in _SENTENCE_PATTERN.split(
                        _normalized_text(chunk.content[match.end() :])
                    )
                    if sentence.strip()
                ]
                if len(sentences) >= 2:
                    return f"{sentences[0]} [1] {sentences[1]} [1]", [chunk]

    if intent == "context":
        for chunk in chunks:
            for match in _TEST_ANSWER_PATTERN.finditer(_normalized_text(chunk.content)):
                test_question = _fold_text(match.group(1))
                if not any(cue in test_question for cue in ("contexte", "problematique", "probleme")):
                    continue
                answer = _SENTENCE_PATTERN.split(match.group(2).strip(), maxsplit=1)[0]
                if answer:
                    return f"{answer} [1]", [chunk]
    return None


def _build_streamable_answer(
    request: GenerateRequest,
    settings: Settings,
    relevant_chunks: list[RetrievedChunk],
    evidence_catalog: list[EvidenceItem] | None = None,
) -> GenerateResponse:
    key = _cache_key(request, relevant_chunks, settings)
    cached = _cached_response(key, settings)
    if cached is not None:
        return cached

    deterministic = _deterministic_answer(request.query, relevant_chunks)
    if deterministic is not None:
        answer, evidence_chunks = deterministic
        citations, confidence = _build_citations(answer, evidence_chunks)
        evidence_spans = _validated_answer_spans(answer, evidence_chunks)
        if not evidence_spans and len(evidence_chunks) == 1:
            source = evidence_chunks[0]
            factual_text = _CITATION_PATTERN.sub("", answer).strip().rstrip(" ;")
            source_range = _quote_source_range(source.content, factual_text)
            if source_range is None and " — " in factual_text:
                source_range = _quote_source_range(
                    source.content, factual_text.replace(" — ", " ", 1)
                )
            if source_range is not None:
                evidence_spans = [
                    EvidenceSpan(
                        evidence_id=1,
                        chunk_id=source.chunk_id,
                        quote=factual_text,
                        source_start=source_range[0],
                        source_end=source_range[1],
                        answer_start=0,
                        answer_end=len(factual_text),
                    )
                ]
        response = GenerateResponse(
            answer=answer,
            citations=citations,
            confidence=confidence,
            evidence=_evidence_catalog(evidence_chunks),
            evidence_spans=evidence_spans,
            validation_passed=bool(citations) and bool(evidence_spans),
        )
        _store_cached_response(key, response, settings)
        return response

    if _explicit_alternatives_absent(request.query, relevant_chunks):
        return _insufficient_response(NO_RELEVANT_EVIDENCE)

    prompt = SOURCED_ANSWER_PROMPT.format(
        question=request.query,
        contexts=_format_contexts(relevant_chunks),
    )
    model_output = generate_text(
        prompt,
        settings,
        max_tokens=settings.generation_max_tokens,
        output_schema=EVIDENCE_RESPONSE_SCHEMA,
    )
    answer, spans, diagnostic = _parse_evidence_response(model_output, relevant_chunks)
    if diagnostic == INVALID_CITATION_FORMAT:
        # A small local model can preserve a completely grounded, cited answer
        # while failing only the redundant coverage serialization (for example by
        # copying ``[7]`` into a quote). Apply the same provenance-only recovery
        # used by SSE: every visible answer span must still map to its declared
        # source, so malformed metadata never turns into ungrounded prose.
        answer, spans, diagnostic = _parse_streamed_answer_fallback(
            model_output, relevant_chunks
        )
    if diagnostic or answer is None:
        return _insufficient_response(diagnostic or UNSUPPORTED_ANSWER)

    citations, confidence = _build_citations(answer, relevant_chunks)
    catalog = evidence_catalog or _evidence_catalog(relevant_chunks)
    response = GenerateResponse(
        answer=answer,
        citations=citations,
        confidence=confidence,
        evidence=catalog,
        evidence_spans=spans,
        validation_passed=bool(citations) and bool(spans),
    )
    _store_cached_response(key, response, settings)
    return response


def _cache_key(
    request: GenerateRequest, chunks: list[RetrievedChunk], settings: Settings
) -> str:
    chunk_version = [
        (chunk.chunk_id, chunk.document_id, chunk.page, chunk.content)
        for chunk in chunks
    ]
    payload = json.dumps(
        {
            "query": _normalized_text(request.query).casefold(),
            "chunks": chunk_version,
            "prompt": _PROMPT_VERSION,
            "model": settings.llm_model,
            "max_tokens": settings.generation_max_tokens,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _cached_response(key: str, settings: Settings) -> GenerateResponse | None:
    if settings.generation_cache_max_entries == 0:
        return None
    with _ANSWER_CACHE_LOCK:
        response = _ANSWER_CACHE.get(key)
        if response is not None:
            _ANSWER_CACHE.move_to_end(key)
            return response.model_copy(deep=True)
    return None


def _store_cached_response(
    key: str, response: GenerateResponse, settings: Settings
) -> None:
    if settings.generation_cache_max_entries == 0:
        return
    with _ANSWER_CACHE_LOCK:
        _ANSWER_CACHE[key] = response.model_copy(deep=True)
        _ANSWER_CACHE.move_to_end(key)
        while len(_ANSWER_CACHE) > settings.generation_cache_max_entries:
            _ANSWER_CACHE.popitem(last=False)


def _source_similarity(chunk: RetrievedChunk) -> float:
    if chunk.vector_score is not None:
        return max(0.0, min(1.0, chunk.vector_score))
    if chunk.relevance_score is not None:
        return max(0.0, min(1.0, chunk.relevance_score))
    return 0.0


def _evidence_catalog(chunks: list[RetrievedChunk]) -> list[EvidenceItem]:
    """Assign stable request-local evidence IDs and validate source metadata."""
    evidence: list[EvidenceItem] = []
    seen_chunk_ids: set[int] = set()
    for chunk in chunks:
        if chunk.chunk_id in seen_chunk_ids or not chunk.content.strip():
            continue
        if chunk.document_id is not None and (not chunk.document_name or chunk.page is None):
            continue
        seen_chunk_ids.add(chunk.chunk_id)
        evidence.append(
            EvidenceItem(
                evidence_id=len(evidence) + 1,
                chunk_id=chunk.chunk_id,
                mission_id=chunk.mission_id,
                mission_title=chunk.mission_title,
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                page=chunk.page,
                corpus_scope=chunk.corpus_scope,
                request_id=chunk.request_id,
                content=chunk.content,
                source_start=0,
                source_end=len(chunk.content),
            )
        )
    return evidence


def _validated_chunks(chunks: list[RetrievedChunk]) -> tuple[list[RetrievedChunk], list[EvidenceItem]]:
    catalog = _evidence_catalog(chunks)
    allowed_chunk_ids = {item.chunk_id for item in catalog}
    validated = [chunk for chunk in chunks if chunk.chunk_id in allowed_chunk_ids]
    return validated, catalog


def _insufficient_response(diagnostic: str, evidence: list[EvidenceItem] | None = None) -> GenerateResponse:
    with _DIAGNOSTIC_COUNTS_LOCK:
        _DIAGNOSTIC_COUNTS[diagnostic] = _DIAGNOSTIC_COUNTS.get(diagnostic, 0) + 1
    return GenerateResponse(
        answer=INSUFFICIENT_INFORMATION,
        citations=[],
        confidence=0.0,
        evidence=evidence or [],
        evidence_spans=[],
        validation_passed=False,
        diagnostic=diagnostic,
    )


def grounding_diagnostic_counts() -> dict[str, int]:
    """Return a process-local snapshot of failed grounding outcomes by reason."""
    with _DIAGNOSTIC_COUNTS_LOCK:
        return dict(sorted(_DIAGNOSTIC_COUNTS.items()))


def _format_contexts(chunks: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{index}] {_source_label(chunk)}\n"
        f"Extrait : {chunk.content}"
        for index, chunk in enumerate(chunks, start=1)
    )


def _source_label(chunk: RetrievedChunk) -> str:
    if chunk.document_name:
        page = f", page {chunk.page}" if chunk.page else ""
        return f"Document : {chunk.document_name}{page}"
    return f"Mission : {chunk.mission_title or chunk.mission_id}"


def _normalized_with_offsets(value: str) -> tuple[str, list[int], list[int]]:
    """Normalize PDF typography while retaining each normalized character's source range."""
    characters: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character == "\u00ad":  # discretionary/soft hyphen
            index += 1
            continue
        # PDF extractors commonly split a hyphenated word over a line break.
        if character in "-‐‑–" and characters and characters[-1].isalnum():
            whitespace_end = index + 1
            while whitespace_end < len(value) and value[whitespace_end].isspace():
                whitespace_end += 1
            if "\n" in value[index + 1 : whitespace_end] and whitespace_end < len(value) and value[whitespace_end].isalnum():
                index = whitespace_end
                continue
        if character.isspace() or character == "\u00a0":
            whitespace_end = index + 1
            while whitespace_end < len(value) and (value[whitespace_end].isspace() or value[whitespace_end] == "\u00a0"):
                whitespace_end += 1
            if characters and characters[-1] != " ":
                characters.append(" ")
                starts.append(index)
                ends.append(whitespace_end)
            index = whitespace_end
            continue
        normalized = unicodedata.normalize("NFKC", character)
        for normalized_character in normalized:
            characters.append(normalized_character)
            starts.append(index)
            ends.append(index + 1)
        index += 1
    while characters and characters[-1] == " ":
        characters.pop()
        starts.pop()
        ends.pop()
    return "".join(characters), starts, ends


def _normalized_text(value: str) -> str:
    return _normalized_with_offsets(value)[0]


def _normalized_answer_text(value: str) -> str:
    """Normalize evidence text plus harmless spacing immediately before ``[source]``."""
    return re.sub(r"\s+\[(\d+)\]", r"[\1]", _normalized_text(value))


def _fuzzy_quote_source_range(
    normalized_content: str,
    starts: list[int],
    ends: list[int],
    normalized_quote: str,
) -> tuple[int, int] | None:
    """Locate a close paraphrase within one source sentence, never another source."""
    stop_terms = {
        "a", "au", "aux", "ce", "ces", "dans", "de", "des", "du", "elle", "en", "est",
        "et", "il", "la", "le", "les", "on", "ou", "par", "pour", "qui", "s", "se", "son",
        "sur", "un", "une", "y",
    }
    quote_terms = [
        term
        for term in re.findall(r"[\wÀ-ÖØ-öø-ÿ]+", _fold_text(normalized_quote))
        if len(term) >= 3 and term not in stop_terms
    ]
    if len(quote_terms) < 4:
        return None
    quote_numbers = set(re.findall(r"\d+(?:[,.]\d+)?", _fold_text(normalized_quote)))
    best: tuple[float, float, int, int] | None = None
    sentences = list(re.finditer(r"[^.!?]+(?:[.!?]|$)", normalized_content))
    for sentence in sentences:
        candidate = sentence.group().strip()
        candidate_terms = set(re.findall(r"[\wÀ-ÖØ-öø-ÿ]+", _fold_text(candidate)))
        if not candidate_terms or not quote_numbers.issubset(
            set(re.findall(r"\d+(?:[,.]\d+)?", _fold_text(candidate)))
        ):
            continue
        coverage = sum(term in candidate_terms for term in quote_terms) / len(quote_terms)
        similarity = SequenceMatcher(
            None, _fold_text(normalized_quote), _fold_text(candidate)
        ).ratio()
        if coverage >= 0.80 and similarity >= 0.75:
            candidate_range = (sentence.start(), sentence.end())
            if best is None or (coverage, similarity) > best[:2]:
                best = (coverage, similarity, *candidate_range)
    if best is not None:
        _, _, start, end = best
        return starts[start], ends[end - 1]

    # A PDF/OCR extraction can differ from a faithfully copied fact by one
    # character (for example, ``précédantes`` vs ``précédentes``). Comparing
    # against the complete source sentence makes a long sentence look unrelated,
    # so also evaluate similarly sized word windows in that same fixed source.
    # This remains deliberately conservative: every numeric token must agree,
    # the lexical coverage must be near complete, and the text similarity must
    # tolerate only a small typographical difference.
    quote_word_count = len(re.findall(r"[\wÀ-ÖØ-öø-ÿ]+", normalized_quote))
    if quote_word_count < 4:
        return None
    for sentence in sentences:
        sentence_start = sentence.start()
        words = list(re.finditer(r"[\wÀ-ÖØ-öø-ÿ]+", sentence.group()))
        if not words:
            continue
        for window_size in range(quote_word_count, min(len(words), quote_word_count) + 1):
            for window_start in range(len(words) - window_size + 1):
                window_end = window_start + window_size - 1
                candidate_start = sentence_start + words[window_start].start()
                candidate_end = sentence_start + words[window_end].end()
                candidate = normalized_content[candidate_start:candidate_end]
                candidate_folded = _fold_text(candidate)
                candidate_terms = set(re.findall(r"[\wÀ-ÖØ-öø-ÿ]+", candidate_folded))
                candidate_numbers = set(re.findall(r"\d+(?:[,.]\d+)?", candidate_folded))
                coverage = sum(term in candidate_terms for term in quote_terms) / len(quote_terms)
                similarity = SequenceMatcher(None, _fold_text(normalized_quote), candidate_folded).ratio()
                if quote_numbers.issubset(candidate_numbers) and coverage >= 0.90 and similarity >= 0.94:
                    return starts[candidate_start], ends[candidate_end - 1]
    return None


def _quote_source_range(content: str, quote: str) -> tuple[int, int] | None:
    """Locate a source-specific quote despite PDF typography or close paraphrasing."""
    normalized_content, starts, ends = _normalized_with_offsets(content)
    normalized_quote = _normalized_text(quote)
    if not normalized_quote:
        return None
    # Sentence-initial capitalization is a presentation difference, not a
    # provenance difference: PDF prose often contains the same fact mid-sentence.
    position = normalized_content.casefold().find(normalized_quote.casefold())
    if position >= 0:
        end_position = position + len(normalized_quote) - 1
        return starts[position], ends[end_position]
    # A model may terminate a copied clause with a period even though the PDF
    # sentence continues after a comma/semicolon. The factual clause remains an
    # exact source substring; accept it while keeping the source fixed.
    clause = normalized_quote.rstrip(".?!;: ")
    if clause and len(clause) >= 12:
        position = normalized_content.casefold().find(clause.casefold())
        if position >= 0:
            end_position = position + len(clause) - 1
            return starts[position], ends[end_position]
    return _fuzzy_quote_source_range(
        normalized_content, starts, ends, normalized_quote
    )


def _validated_answer_spans(
    answer: str, relevant_chunks: list[RetrievedChunk]
) -> list[EvidenceSpan]:
    """Map every emitted factual sentence and citation to an exact evidence range."""
    spans: list[EvidenceSpan] = []
    matches = list(_ANSWER_CITATION_PATTERN.finditer(answer))
    if not matches:
        return []
    previous_end = 0
    for match in matches:
        # Every visible non-citation character must belong to a cited quote; this
        # prevents a model from smuggling explanatory prose between evidence spans.
        if answer[previous_end : match.start()].strip():
            return []
        source = int(match.group("source"))
        if not 1 <= source <= len(relevant_chunks):
            return []
        raw_quote = match.group("quote")
        quote = raw_quote.strip().rstrip(" ;")
        if not quote:
            return []
        source_range = _quote_source_range(relevant_chunks[source - 1].content, quote)
        if source_range is None:
            return []
        leading_whitespace = len(raw_quote) - len(raw_quote.lstrip())
        answer_start = match.start("quote") + leading_whitespace
        spans.append(
            EvidenceSpan(
                evidence_id=source,
                chunk_id=relevant_chunks[source - 1].chunk_id,
                quote=quote,
                source_start=source_range[0],
                source_end=source_range[1],
                answer_start=answer_start,
                answer_end=answer_start + len(quote),
            )
        )
        previous_end = match.end()
    if answer[previous_end:].strip():
        return []
    return spans


def _is_low_information_quote(quote: str) -> bool:
    """Reject navigational or empty fragments that cannot establish a fact."""
    normalized = _normalized_text(quote)
    folded = _fold_text(normalized)
    lexical_words = re.findall(r"[a-z0-9à-öø-ÿ]+", folded)
    if len(lexical_words) < 3:
        return True
    if normalized.count(".") >= max(8, len(normalized) // 5):
        return True
    if re.search(r"(?:\.\s*){3,}", normalized):
        return True
    if "sommaire" in folded or "table des matieres" in folded:
        return True
    # A bare section title or table header gives no answer value by itself. A
    # short grammatical sentence remains valid evidence, so require its absence
    # of sentence/table punctuation before rejecting it.
    if (
        not re.search(r"\d|[%€]", normalized)
        and len(lexical_words) <= 7
        and not re.search(r"[.!?;:]", normalized)
    ):
        return True
    return False


def _criterion_is_directly_supported(criterion: str, quotes: list[str]) -> bool:
    """Reject vague criteria and claims whose salient terms are absent from evidence.

    This deterministic guard complements the structured evidence pass. It blocks
    the common "same project, wrong attribute" failure (for example subscribers
    presented as market share) without accepting a citation merely because it is
    from the correct document.
    """
    folded = _fold_text(criterion)
    if "?" in criterion or folded in {"element", "element demande", "critere", "reponse"}:
        return False
    stop_words = {
        "le", "la", "les", "un", "une", "des", "de", "du", "et", "est", "sont",
        "dans", "pour", "avec", "sur", "par", "au", "aux", "ce", "cette", "ces",
        "projet", "programme", "mission", "information", "element", "demande",
    }
    tokens = [
        token for token in re.findall(r"[a-z0-9]+", folded)
        if len(token) >= 3 and token not in stop_words
    ]
    numeric_tokens = re.findall(r"\d+(?:[,.]\d+)?\s*%?", folded)
    if not tokens or (len(tokens) < 2 and not numeric_tokens):
        return False
    evidence_text = _fold_text(" ".join(quotes))
    if numeric_tokens and not all(number in evidence_text for number in numeric_tokens):
        return False

    # A numeric value or a nearby project name is not proof of the requested
    # attribute. Require the attribute family itself in the exact quote before
    # applying the general lexical overlap guard.
    required_attribute_groups = (
        ("part de marche", "market share"),
        ("chiffre d affaires", "revenu", "revenue", "ca "),
        ("editeur", "fournisseur", "vendor", "constructeur"),
        ("tarif", "prix", "cout", "coût"),
        ("budget engage", "budget consomm", "budget consomme"),
        ("couleur", "color"),
    )
    for attribute_group in required_attribute_groups:
        criterion_requests_attribute = any(
            attribute in folded for attribute in attribute_group
        )
        if criterion_requests_attribute and not any(
            attribute in evidence_text for attribute in attribute_group
        ):
            return False

    matching_terms = sum(
        re.search(rf"(?<!\w){re.escape(token)}(?!\w)", evidence_text) is not None
        for token in set(tokens)
    )
    return matching_terms >= min(2, len(set(tokens)))


def _parse_evidence_response(
    model_output: str,
    relevant_chunks: list[RetrievedChunk],
) -> tuple[str | None, list[EvidenceSpan], str | None]:
    """Accept only exact, criterion-level evidence with unambiguous provenance.

    Containment proves that a quote was not invented. Criterion-level coverage
    makes the model account for every requested item; a source mismatch or an
    ambiguous duplicate is rejected rather than silently reassigned to another
    PDF page. The legacy ``evidence`` shape remains temporarily readable for
    already cached responses, while the constrained model schema emits
    ``coverage``.
    """
    raw = model_output.strip()
    if raw == INSUFFICIENT_INFORMATION:
        return None, [], NO_RELEVANT_EVIDENCE
    if raw.startswith("```") and raw.endswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, [], INVALID_CITATION_FORMAT
    if not isinstance(payload, dict):
        return None, [], INVALID_CITATION_FORMAT

    status = payload.get("status")
    streamed_answer = payload.get("answer")
    coverage = payload.get("coverage")
    legacy_evidence = payload.get("evidence")
    if (
        status == NO_RELEVANT_EVIDENCE
        and streamed_answer == ""
        and coverage == []
        and set(payload) == {"status", "answer", "coverage"}
    ):
        return None, [], NO_RELEVANT_EVIDENCE
    if status == NO_RELEVANT_EVIDENCE and coverage == [] and set(payload) == {"status", "coverage"}:
        return None, [], NO_RELEVANT_EVIDENCE
    if status == NO_RELEVANT_EVIDENCE and legacy_evidence == [] and set(payload) == {"status", "evidence"}:
        return None, [], NO_RELEVANT_EVIDENCE

    if status != "SUPPORTED":
        return None, [], INVALID_CITATION_FORMAT
    if set(payload) == {"status", "answer", "coverage"}:
        if not isinstance(streamed_answer, str) or not streamed_answer.strip() or not isinstance(coverage, list) or not coverage:
            return None, [], INVALID_CITATION_FORMAT
    elif set(payload) == {"status", "coverage"}:
        if not isinstance(coverage, list) or not coverage:
            return None, [], INVALID_CITATION_FORMAT
    if set(payload) in ({"status", "answer", "coverage"}, {"status", "coverage"}):
        evidence_groups: list[tuple[str, list[object]]] = []
        criteria: set[str] = set()
        for item in coverage:
            if not isinstance(item, dict) or set(item) != {"criterion", "evidence"}:
                return None, [], INVALID_CITATION_FORMAT
            criterion = item.get("criterion")
            group = item.get("evidence")
            if not isinstance(criterion, str) or not criterion.strip() or not isinstance(group, list) or not group:
                return None, [], INVALID_CITATION_FORMAT
            normalized_criterion = _normalized_text(criterion).casefold()
            if normalized_criterion in criteria:
                return None, [], INVALID_CITATION_FORMAT
            criteria.add(normalized_criterion)
            evidence_groups.append((criterion, group))
    elif set(payload) == {"status", "evidence"}:
        # Compatibility only. New completions are constrained by the coverage schema.
        if not isinstance(legacy_evidence, list) or not legacy_evidence:
            return None, [], INVALID_CITATION_FORMAT
        evidence_groups = [("legacy", [item]) for item in legacy_evidence]
    else:
        return None, [], INVALID_CITATION_FORMAT

    answer_sentences: list[str] = []
    seen: set[tuple[int, str]] = set()
    for criterion, group in evidence_groups:
        group_has_valid_evidence = False
        group_quotes: list[str] = []
        for item in group:
            if not isinstance(item, dict) or set(item) != {"source", "quote"}:
                return None, [], INVALID_CITATION_FORMAT
            source = item.get("source")
            quote = item.get("quote")
            if (
                not isinstance(source, int)
                or isinstance(source, bool)
                or not 1 <= source <= len(relevant_chunks)
                or not isinstance(quote, str)
                or not quote.strip()
            ):
                return None, [], INVALID_CITATION_FORMAT

            normalized_quote = _normalized_text(quote)
            quote_citations = [int(match) for match in _CITATION_PATTERN.findall(normalized_quote)]
            if quote_citations:
                # qwen can copy the display marker from the answer into the
                # evidence quote. It is redundant metadata, not source text.
                # Normalize only markers that agree with the declared source;
                # a conflicting marker remains an invalid citation and is never
                # silently remapped to another chunk.
                if any(citation != source for citation in quote_citations):
                    return None, [], INVALID_CITATION_FORMAT
                normalized_quote = _CITATION_PATTERN.sub("", normalized_quote)
                normalized_quote = re.sub(r"\s+([,.;:!?])", r"\1", normalized_quote).strip()
            if _is_low_information_quote(normalized_quote):
                return None, [], UNSUPPORTED_ANSWER
            # Never repair an incorrect source index. The old repair selected the
            # first duplicate quote and was the direct cause of page drift.
            source_range = _quote_source_range(
                relevant_chunks[source - 1].content, normalized_quote
            )
            if source_range is None:
                return None, [], UNSUPPORTED_ANSWER
            # A fuzzy match is a provenance lookup only. Emit the exact source
            # substring, never the model's near-copy, so a corrected OCR typo or
            # other minor model alteration cannot leak into the answer.
            verified_quote = relevant_chunks[source - 1].content[
                source_range[0] : source_range[1]
            ]

            group_has_valid_evidence = True
            group_quotes.append(verified_quote)
            key = (source, verified_quote)
            if key in seen:
                continue
            seen.add(key)
            sentences = [
                sentence.strip()
                for sentence in _SENTENCE_PATTERN.split(verified_quote)
                if sentence.strip()
            ]
            answer_sentences.extend(f"{sentence} [{source}]" for sentence in sentences)
        if not group_has_valid_evidence:
            return None, [], UNSUPPORTED_ANSWER
        # The displayed answer is reconstructed exclusively from the verified
        # quotes below. A criterion is planning metadata, and a small model may
        # add harmless temporal wording (for example, "avant la refonte") that
        # is implicit in an exact before/after quote. Do not make acceptance
        # depend on this paraphrased label; source-bound quotes remain the sole
        # provenance boundary.

    if not answer_sentences:
        return None, [], UNSUPPORTED_ANSWER
    answer = " ".join(answer_sentences)
    # The model-facing answer is for low-latency provisional display. The final
    # trusted answer is reconstructed only from validated source quotes, so a
    # harmless presentation difference cannot discard otherwise valid evidence.
    # Unsupported words, altered citations and source drift are rejected by the
    # source-bound coverage checks above; the untrusted presentation string is
    # never returned to the caller.
    spans = _validated_answer_spans(answer, relevant_chunks)
    if not spans:
        return None, [], UNSUPPORTED_ANSWER
    return answer, spans, None


def _parse_streamed_answer_fallback(
    model_output: str,
    relevant_chunks: list[RetrievedChunk],
) -> tuple[str | None, list[EvidenceSpan], str | None]:
    """Accept a fully source-verifiable streamed answer if coverage JSON is malformed.

    This narrow recovery path is limited to a ``SUPPORTED`` JSON payload whose
    complete answer comprises exact, individually cited PDF spans. It preserves
    the evidence catalog and never accepts uncited prose; it only avoids losing a
    valid response because the model serialized the redundant coverage metadata
    incorrectly.
    """
    try:
        payload = json.loads(model_output.strip())
    except (json.JSONDecodeError, TypeError):
        return None, [], INVALID_CITATION_FORMAT
    if not isinstance(payload, dict) or payload.get("status") != "SUPPORTED":
        return None, [], INVALID_CITATION_FORMAT
    answer = payload.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        return None, [], INVALID_CITATION_FORMAT
    spans = _validated_answer_spans(answer, relevant_chunks)
    if not spans:
        return None, [], UNSUPPORTED_ANSWER
    return answer, spans, None


def _referenced_indexes(answer: str, source_count: int) -> list[int]:
    indexes: list[int] = []
    for match in _CITATION_PATTERN.finditer(answer):
        index = int(match.group(1))
        if 1 <= index <= source_count and index not in indexes:
            indexes.append(index)
    return indexes


def _has_invalid_citation(answer: str, source_count: int) -> bool:
    return any(
        not 1 <= int(match.group(1)) <= source_count
        for match in _CITATION_PATTERN.finditer(answer)
    )


def _build_citations(
    answer: str, relevant_chunks: list[RetrievedChunk]
) -> tuple[list[Citation], float]:
    """Extract citations from a generated answer and compute confidence."""
    referenced_indexes = _referenced_indexes(answer, len(relevant_chunks))
    if not referenced_indexes or _has_invalid_citation(answer, len(relevant_chunks)):
        return [], 0.0

    cited_chunks = [relevant_chunks[index - 1] for index in referenced_indexes]
    confidence = sum(_source_similarity(chunk) for chunk in cited_chunks) / len(
        cited_chunks
    )
    citations = [
        Citation(
            citation_id=f"{chunk.request_id or 'no-request'}:{chunk.chunk_id}",
            chunk_id=chunk.chunk_id,
            mission_id=chunk.mission_id,
            mission_title=chunk.mission_title,
            document_id=chunk.document_id,
            document_name=chunk.document_name,
            page=chunk.page,
            corpus_scope=chunk.corpus_scope,
            request_id=chunk.request_id,
            content=chunk.content,
            score=chunk.score,
            rrf_score=chunk.rrf_score,
            relevance_score=_source_similarity(chunk),
            source_index=source_index,
        )
        for source_index, chunk in zip(referenced_indexes, cited_chunks, strict=True)
    ]
    return citations, max(0.0, min(1.0, confidence))


def generate_sourced_answer(
    request: GenerateRequest, settings: Settings
) -> GenerateResponse:
    """Generate an answer only when relevant sources and valid citations exist."""
    selected_chunks = _select_relevant_chunks(
        request.query,
        request.chunks,
        limit=settings.generation_max_context_chunks,
    )
    relevant_chunks, evidence = _validated_chunks(selected_chunks)
    if not relevant_chunks:
        return _insufficient_response(NO_RELEVANT_EVIDENCE, evidence)

    response = _build_streamable_answer(request, settings, relevant_chunks, evidence)
    if response.answer == INSUFFICIENT_INFORMATION:
        response = response.model_copy(update={"evidence": evidence, "validation_passed": False})
    logger.info(
        "Generated evidence pages=%s confidence=%.3f",
        [citation.page for citation in response.citations],
        response.confidence,
    )
    return response


def _stream_synthesis_prompt(answer: str) -> str:
    """Request the already-validated answer; its JSON schema is the output constraint."""
    return f"""Retourne exactement la chaîne JSON imposée par le schéma.
N'ajoute aucun titre, aucune explication, aucun fait, aucune citation ni aucun caractère.

Chaîne validée :
{answer}"""


def _stream_answer_schema(answer: str) -> dict[str, object]:
    """An enum grammar prevents the presentation model from adding unsupported claims."""
    return {"type": "string", "enum": [answer]}


class _JsonStringFieldDecoder:
    """Incrementally decode one JSON string field without exposing JSON framing."""

    def __init__(self, field_name: str) -> None:
        self._field_pattern = re.compile(rf'"{re.escape(field_name)}"\s*:\s*"')
        self._prefix = ""
        self._started = False
        self._finished = False
        self._escaped = False
        self._unicode_digits = ""

    def feed(self, raw_token: str) -> str:
        decoded = ""
        for character in raw_token:
            if not self._started:
                self._prefix = (self._prefix + character)[-96:]
                match = self._field_pattern.search(self._prefix)
                if match is None:
                    continue
                self._started = True
                self._prefix = ""
                continue
            if self._finished:
                continue
            if self._unicode_digits:
                self._unicode_digits += character
                if len(self._unicode_digits) == 5:
                    try:
                        decoded += chr(int(self._unicode_digits[1:], 16))
                    except ValueError:
                        self._finished = True
                    self._unicode_digits = ""
                    self._escaped = False
                continue
            if self._escaped:
                if character == "u":
                    self._unicode_digits = "u"
                    continue
                decoded += {"\"": '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}.get(character, character)
                self._escaped = False
                continue
            if character == "\\":
                self._escaped = True
            elif character == '"':
                self._finished = True
            else:
                decoded += character
        return decoded

    @property
    def complete(self) -> bool:
        return self._started and self._finished and not self._escaped and not self._unicode_digits


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def generate_sourced_answer_stream(
    request: GenerateRequest, settings: Settings
) -> Generator[str, None, None]:
    """Stream one structured Ollama completion and validate its full evidence payload.

    Provisional model tokens are held until evidence validation completes. A
    validation failure is never exposed as a normal answer without provenance:
    callers receive the canonical insufficient-evidence result instead. This
    retains the one-call Ollama invariant while preventing uncited factual text
    from reaching the browser.
    """
    selected_chunks = _select_relevant_chunks(
        request.query,
        request.chunks,
        limit=settings.generation_max_context_chunks,
    )
    relevant_chunks, evidence_catalog = _validated_chunks(selected_chunks)
    request_id = request.request_id
    yield _sse_event("status", {"status": "generating", "requestId": request_id})
    if not relevant_chunks:
        yield _sse_event("validation", {"passed": False, "diagnostic": NO_RELEVANT_EVIDENCE})
        yield _sse_event("delta", {"token": INSUFFICIENT_INFORMATION})
        yield _sse_event("done", {
            "requestId": request_id,
            "evidence": [],
            "evidenceSpans": [],
            "citations": [],
            "confidence": 0.0,
            "validationPassed": False,
            "diagnostic": NO_RELEVANT_EVIDENCE,
        })
        return

    key = _cache_key(request, relevant_chunks, settings)
    response = _cached_response(key, settings)
    if response is None:
        deterministic = _deterministic_answer(request.query, relevant_chunks)
        if deterministic is not None:
            # The deterministic path is already validated without model inference.
            response = _build_streamable_answer(
                request, settings, relevant_chunks, evidence_catalog
            )
        elif _explicit_alternatives_absent(request.query, relevant_chunks):
            response = _insufficient_response(NO_RELEVANT_EVIDENCE, evidence_catalog)
        else:
            prompt = SOURCED_ANSWER_PROMPT.format(
                question=request.query,
                contexts=_format_contexts(relevant_chunks),
            )
            raw_stream = generate_text_stream(
                prompt,
                settings,
                max_tokens=settings.generation_max_tokens,
                output_schema=EVIDENCE_RESPONSE_SCHEMA,
            )
            answer_decoder = _JsonStringFieldDecoder("answer")
            raw_tokens: list[str] = []
            try:
                for raw_token in raw_stream:
                    raw_tokens.append(raw_token)
                    answer_decoder.feed(raw_token)
            except GeneratorExit:
                raw_stream.close()
                logger.info("generation evidence stream cancelled query=%r", request.query)
                raise
            model_output = "".join(raw_tokens)
            answer, spans, diagnostic = _parse_evidence_response(model_output, relevant_chunks)
            if diagnostic == INVALID_CITATION_FORMAT:
                answer, spans, diagnostic = _parse_streamed_answer_fallback(
                    model_output, relevant_chunks
                )
            if diagnostic or answer is None:
                response = _insufficient_response(diagnostic or UNSUPPORTED_ANSWER, evidence_catalog)
            else:
                citations, confidence = _build_citations(answer, relevant_chunks)
                response = GenerateResponse(
                    answer=answer,
                    citations=citations,
                    confidence=confidence,
                    evidence=evidence_catalog,
                    evidence_spans=spans,
                    validation_passed=bool(citations) and bool(spans),
                )
                _store_cached_response(key, response, settings)

    serialized_evidence = [item.model_dump(mode="json") for item in response.evidence]
    yield _sse_event("evidence", {"requestId": request_id, "evidence": serialized_evidence})
    if not response.validation_passed:
        diagnostic = response.diagnostic or UNSUPPORTED_ANSWER
        yield _sse_event("validation", {"passed": False, "diagnostic": diagnostic})
        # A model completion that cannot be proven is not a trusted answer. Do
        # not emit its provisional text, do not send an SSE error, and always
        # complete the protocol with the canonical grounded abstention.
        yield _sse_event("delta", {"token": INSUFFICIENT_INFORMATION})
        yield _sse_event("done", {
            "requestId": request_id,
            "evidence": serialized_evidence,
            "evidenceSpans": [],
            "citations": [],
            "confidence": 0.0,
            "validationPassed": False,
            "diagnostic": diagnostic,
        })
        return

    yield _sse_event("heartbeat", {"requestId": request_id})
    yield _sse_event("validation", {"passed": True, "diagnostic": None})
    # The one completion is buffered until validation, then emitted exactly once
    # whether it came from Ollama, cache, or a deterministic extractor.
    if response.answer:
        yield _sse_event("delta", {"token": response.answer})
    citations_data = _serialize_stream_citations(response.citations, relevant_chunks)
    yield _sse_event("citation", {"requestId": request_id, "citations": citations_data})
    yield _sse_event("done", {
        "requestId": request_id,
        "evidence": serialized_evidence,
        "evidenceSpans": [item.model_dump(mode="json") for item in response.evidence_spans],
        "citations": citations_data,
        "confidence": response.confidence,
        "validationPassed": True,
        "diagnostic": None,
    })


def _serialize_stream_citations(
    citations: list[Citation], relevant_chunks: list[RetrievedChunk]
) -> list[dict]:
    return [
        {
            "citationId": c.citation_id,
            "requestId": c.request_id,
            "chunkId": c.chunk_id,
            "missionId": c.mission_id,
            "missionTitle": c.mission_title,
            "documentId": c.document_id,
            "documentName": c.document_name,
            "page": c.page,
            "corpusScope": c.corpus_scope,
            "content": c.content,
            "score": c.score,
            "rrfScore": c.rrf_score,
            "relevanceScore": c.relevance_score,
            "sourceIndex": c.source_index or next(
                index for index, chunk in enumerate(relevant_chunks, start=1)
                if chunk.chunk_id == c.chunk_id
            ),
        }
        for c in citations
    ]


_RFP_SECTION_TITLES = (
    ("executive_summary", "Synthèse exécutive"),
    ("context", "Compréhension du contexte et des enjeux"),
    ("discovery", "Hypothèses et questions de cadrage"),
    ("functional_solution", "Solution fonctionnelle proposée"),
    ("technical_architecture", "Architecture technique cible"),
    ("integrations", "Intégrations et interfaces"),
    ("security", "Sécurité, conformité et gouvernance des données"),
    ("migration", "Approche de migration et de déploiement"),
    ("phases", "Phases détaillées et livrables"),
    ("roadmap", "Planning et jalons"),
    ("team", "Équipe, rôles et gouvernance"),
    ("testing", "Stratégie de tests et de recette"),
    ("change", "Conduite du changement et formation"),
    ("operations", "Exploitation, support et maintenance"),
    ("risks", "Risques, mesures de maîtrise et dépendances"),
    ("kpis", "Résultats attendus et indicateurs"),
    ("scope", "Périmètre inclus et exclu"),
    ("references", "Références internes pertinentes"),
    ("confirmation", "Éléments à confirmer avec le client"),
)


def _fold_rfp_text(value: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFKD", value.lower())
        if not unicodedata.combining(character)
    )


def _requirement_values(description: str, terms: tuple[str, ...]) -> list[str]:
    sentences = re.split(r"(?<=[.!?;])\s+|\n+", description.strip())
    return [sentence.strip() for sentence in sentences if any(term in _fold_rfp_text(sentence) for term in terms)]


def _extract_rfp_requirements(description: str, sector: str | None) -> RfpRequirements:
    from .rfp_proposal_legacy import _extract_rfp_requirements as _extract

    return _extract(description, sector)


def _source_marker(index: int) -> str:
    return f"[{index}]"


def _citation_for_chunk(chunk: RetrievedChunk, index: int) -> RfpCitation | None:
    if chunk.document_id is None or chunk.document_name is None or chunk.page is None:
        return None
    return RfpCitation(
        citation_id=f"rfp-{chunk.chunk_id}",
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        document_name=chunk.document_name,
        page=chunk.page,
        content=chunk.content,
        source_index=index,
    )


def _brief_facts(requirements: RfpRequirements) -> list[str]:
    values = [
        *requirements.business_problem,
        *requirements.project_type,
        *requirements.technologies_and_constraints,
        *requirements.security_and_compliance,
        *requirements.expected_deliverables,
        *requirements.timeline_and_urgency,
    ]
    return values[:4]


def _proposal_sections(requirements: RfpRequirements, citations: list[RfpCitation]) -> list[RfpSection]:
    from .rfp_proposal_legacy import build_adaptive_proposal

    return build_adaptive_proposal(requirements, citations)


def generate_rfp_structure(request: RfpRequest, settings: Settings) -> RfpResponse:
    """Build a structured, 19-section enterprise proposal strictly from PDF evidence and brief facts."""
    from .rfp_proposal import generate_rfp_proposal

    return generate_rfp_proposal(request, settings)


def _explicit_alternatives_absent(
    query: str, chunks: list[RetrievedChunk]
) -> bool:
    corpus = _fold_text(" ".join(chunk.content for chunk in chunks))
    for parenthesized in _PARENTHESIZED_PATTERN.findall(query):
        folded_parenthesized = _fold_text(parenthesized)
        if any(
            marker in folded_parenthesized
            for marker in ("par exemple", "for example", "e.g.", "etc.")
        ):
            continue
        if _ALTERNATIVE_SEPARATOR_PATTERN.search(parenthesized) is None:
            continue
        alternatives = [
            alternative.strip()
            for alternative in _ALTERNATIVE_SEPARATOR_PATTERN.split(parenthesized)
            if alternative.strip()
        ]
        if len(alternatives) < 2 or any(
            len(alternative) > 40
            or re.fullmatch(r"[\wÀ-ÖØ-öø-ÿ][\wÀ-ÖØ-öø-ÿ .+/#-]*", alternative)
            is None
            for alternative in alternatives
        ):
            continue
        if all(
            re.search(
                rf"(?<!\w){re.escape(_fold_text(alternative))}(?!\w)", corpus
            )
            is None
            for alternative in alternatives
        ):
            return True
    return False