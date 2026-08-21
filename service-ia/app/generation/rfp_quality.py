"""Deterministic quality gates for RFP generation."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from ..schemas import RfpSection, RfpBullet

_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Ý0-9])")
_WORD_PATTERN = re.compile(r"\b\w+\b")

BOILERPLATE_PHRASES = {
    "il est crucial de",
    "il est essentiel de",
    "nous sommes ravis de",
    "leader sur son marché",
    "dans un monde en perpétuelle évolution",
    "à l'ère du numérique",
    "véritable partenaire",
    "au cœur de notre préoccupation",
    "nous mettons un point d'honneur",
    "forte de son expertise",
    "la clé du succès",
    "incontournable",
    "il va sans dire",
    "comme vous le savez",
    "nous avons la conviction",
    "une approche innovante et sur mesure",
    "un accompagnement de bout en bout",
}


def _fold_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _count_words(text: str) -> int:
    return len(_WORD_PATTERN.findall(text))


def check_boilerplate(text: str) -> list[str]:
    """Return a list of matched boilerplate phrases in the text."""
    if not text:
        return []
    folded = _fold_text(text)
    matches = []
    for phrase in BOILERPLATE_PHRASES:
        if _fold_text(phrase) in folded:
            matches.append(phrase)
    return matches


def enforce_sentence_length(text: str, max_words: int = 25) -> tuple[str, bool]:
    """Split sentences if they exceed max_words. Returns (new_text, modified)."""
    if not text:
        return text, False
        
    sentences = _SENTENCE_SPLIT_PATTERN.split(text)
    new_sentences = []
    modified = False
    
    for sentence in sentences:
        words = _WORD_PATTERN.findall(sentence)
        if len(words) > max_words:
            match = list(re.finditer(r"\b\w+\b", sentence))
            if len(match) > max_words:
                cut_idx = match[max_words - 1].end()
                repaired = sentence[:cut_idx] + "."
                new_sentences.append(repaired)
                modified = True
            else:
                new_sentences.append(sentence)
        else:
            new_sentences.append(sentence)
            
    return " ".join(new_sentences), modified


def check_repeated_8grams(text: str) -> float:
    """Return the ratio of words belonging to repeated 8-grams."""
    words = _WORD_PATTERN.findall(_fold_text(text))
    if len(words) < 16:
        return 0.0
        
    ngrams = []
    for i in range(len(words) - 7):
        ngrams.append(tuple(words[i : i + 8]))
        
    seen = set()
    repeated = set()
    for ngram in ngrams:
        if ngram in seen:
            repeated.add(ngram)
        seen.add(ngram)
        
    if not repeated:
        return 0.0
        
    repeated_word_indices = set()
    for i in range(len(words) - 7):
        ngram = tuple(words[i : i + 8])
        if ngram in repeated:
            for j in range(8):
                repeated_word_indices.add(i + j)
                
    return len(repeated_word_indices) / len(words)


def calculate_info_density(body: str | None, bullets: list[RfpBullet]) -> float:
    """Return anchored info units / words * 100."""
    total_words = 0
    if body:
        total_words += _count_words(body)
    for b in bullets:
        total_words += _count_words(b.text)
        
    if total_words == 0:
        return 100.0 if bullets else 0.0
        
    anchored_units = len([b for b in bullets if b.anchor is not None and b.anchor.id])
    if body:
        anchored_units += len(re.findall(r"\[pdf-\d+\]", body, re.IGNORECASE))
        for pattern in _FACTUAL_VALUE_PATTERNS:
            anchored_units += len(pattern.findall(body))
        
    return (anchored_units / total_words) * 100.0


_CITATION_PATTERN = re.compile(r"\[(pdf-\d+)\]", re.IGNORECASE)
_FACTUAL_VALUE_PATTERNS = (
    re.compile(r"\b\d+[.,]?\d*\s*%"),
    re.compile(r"\b\d+[.,]?\d*\s*(?:ms|millisecondes?|secondes?|minutes?|heures?|jours?|semaines?|mois|ans?)\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    re.compile(r"\b\d+[.,]?\d*\s*(?:k€|m€|€|eur|ke?ur|meur)\b", re.IGNORECASE),
    re.compile(r"\b(?:24/7|24h/24|7j/7|5j/7)\b", re.IGNORECASE),
)
_STOP_WORDS = {"avec", "dans", "pour", "par", "des", "les", "une", "sur", "de", "du", "la", "le", "et", "est", "sont", "nos", "notre", "votre"}


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", _fold_text(value)).strip()


def _visible_texts(section: RfpSection) -> list[str]:
    values = [section.body or "", *(bullet.text for bullet in section.bullets), *section.assumptions, *section.questions]
    for table in section.tables:
        values.extend([table.title, *table.columns])
        values.extend(cell for row in table.rows for cell in row)
    return [value for value in values if value]


def _significant_terms(value: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9à-ÿ]{4,}", _fold_text(value)) if term not in _STOP_WORDS}


def _is_supported_sentence(sentence: str, quote: str) -> bool:
    terms = _significant_terms(_CITATION_PATTERN.sub("", sentence))
    quote_terms = _significant_terms(quote)
    if not terms:
        return True
    return len(terms & quote_terms) >= max(1, min(2, len(terms) // 3))


def validate_section(section: RfpSection, allowed_evidence_ids: list[str] | dict[str, object]) -> list[str]:
    """Apply deterministic quality gates, including factual and citation integrity.

    A mapping contains the canonical request-scoped evidence keyed by `pdf-XXX`;
    it can also carry `__brief__` with the immutable original brief.
    """
    warnings = []
    canonical = allowed_evidence_ids if isinstance(allowed_evidence_ids, dict) else {}
    allowed_ids = {key for key in canonical if not key.startswith("__")} if canonical else set(allowed_evidence_ids)
    original_brief = str(canonical.get("__brief__", "")) if canonical else ""

    # A clarification section intentionally contains questions or caveats rather
    # than fully evidenced commitments; it must still undergo citation and numeric
    # checks below. Only an explicitly non-applicable section has no factual claim
    # to validate.
    if section.status == "not_applicable":
        return warnings

    density = calculate_info_density(section.body, section.bullets)
    if density < 3.0:
        warnings.append(f"Densité d'information insuffisante ({density:.1f} < 3.0)")

    visible_texts = _visible_texts(section)
    combined_text = " ".join(visible_texts)
    body_text = section.body or ""
    ratio = check_repeated_8grams(body_text)
    if ratio > 0.20:
        warnings.append(f"Taux de répétition trop élevé ({ratio:.2%})")
    bp_matches = check_boilerplate(combined_text)
    if bp_matches:
        warnings.append(f"Présence de phrases génériques : {', '.join(bp_matches)}")
    if section.body and any(_count_words(sentence) > 25 for sentence in _SENTENCE_SPLIT_PATTERN.split(section.body)):
        warnings.append("Phrase trop longue (>25 mots) détectée.")

    unanchored = [bullet for bullet in section.bullets if bullet.anchor is None or not bullet.anchor.id]
    if unanchored:
        warnings.append(f"{len(unanchored)} puces sans ancre détectées.")

    raw_markers = _CITATION_PATTERN.findall(combined_text)
    marker_set = {m.lower() for m in raw_markers}
    section.evidence = [ev for ev in section.evidence if ev.id.lower() in marker_set]
    selected_ids = [evidence.id for evidence in section.evidence]
    selected_set = {eid.lower() for eid in selected_ids}

    for evidence_id in selected_ids:
        if not any(evidence_id.lower() == aid.lower() for aid in allowed_ids):
            warnings.append(f"Preuve inconnue ou non autorisée : {evidence_id}")

    for marker in raw_markers:
        if not any(marker.lower() == aid.lower() for aid in allowed_ids):
            warnings.append(f"Citation canonique invalide ou orpheline : [{marker}]")
        elif marker.lower() not in selected_set:
            canon_match = next((k for k in canonical if k.lower() == marker.lower()), None)
            if canon_match and canonical.get(canon_match) and hasattr(canonical[canon_match], "model_copy"):
                section.evidence.append(canonical[canon_match].model_copy(deep=True))
                selected_set.add(canon_match.lower())
            else:
                warnings.append(f"Citation [{marker}] absente des preuves structurées de la section")

    sentences = [sentence for text in visible_texts for sentence in _SENTENCE_SPLIT_PATTERN.split(text)]
    normalized_brief = _normalized(original_brief)
    for sentence in sentences:
        cited_ids = _CITATION_PATTERN.findall(sentence)
        cited_quotes = [str(getattr(canonical.get(evidence_id), "quote", "") or "") for evidence_id in cited_ids]
        for evidence_id, quote in zip(cited_ids, cited_quotes):
            if quote and not _is_supported_sentence(sentence, quote):
                warnings.append(f"Citation non pertinente : [{evidence_id}] ne soutient pas la phrase citée")
        for pattern in _FACTUAL_VALUE_PATTERNS:
            for match in pattern.finditer(sentence):
                value = match.group(0)
                normalized_value = _normalized(value)
                if normalized_value in normalized_brief:
                    continue
                if any(normalized_value in _normalized(quote) for quote in cited_quotes):
                    continue
                warnings.append(f"Valeur factuelle non sourcée ou contradictoire : {value}")
    return warnings


def segment_long_sentences(text: str) -> str:
    if not text:
        return text
    sentences = _SENTENCE_SPLIT_PATTERN.split(text)
    new_sentences = []
    for s in sentences:
        if _count_words(s) > 25:
            broken = False
            for sep in [", ", " et ", " qui ", " que ", " dont "]:
                idx = s.find(sep, 20)
                if idx != -1 and _count_words(s[:idx]) <= 25:
                    new_sentences.append(s[:idx].strip() + ".")
                    new_sentences.append(s[idx + len(sep):].strip().capitalize())
                    broken = True
                    break
            if not broken:
                repaired, _ = enforce_sentence_length(s, 25)
                new_sentences.append(repaired)
        else:
            new_sentences.append(s)
    return " ".join(new_sentences)


def truncate_to_budget(section: RfpSection, budget: int) -> bool:
    """Deterministically clean up and reduce section to word budget."""
    modified = False
    
    # 1. Remove boilerplate
    if section.body:
        for phrase in BOILERPLATE_PHRASES:
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            if pattern.search(section.body):
                section.body = pattern.sub("", section.body)
                modified = True
                
    # 2. Segment long sentences (> 25 words)
    if section.body:
        new_body, body_mod = enforce_sentence_length(section.body, max_words=25)
        if body_mod:
            section.body = new_body
            modified = True
            
    for b in section.bullets:
        if _count_words(b.text) > 25:
            b.text, b_mod = enforce_sentence_length(b.text, max_words=25)
            if b_mod:
                modified = True
                
    # 3. Clean up unanchored bullets
    new_bullets = []
    for b in section.bullets:
        if b.anchor and b.anchor.id:
            new_bullets.append(b)
        else:
            if b.anchor:
                new_bullets.append(b)
            else:
                modified = True
    section.bullets = new_bullets
    
    # 4. Truncate if over budget
    def current_words():
        total = _count_words(section.body or "")
        for b in section.bullets:
            total += _count_words(b.text)
        return total
        
    if current_words() <= budget:
        return modified
        
    # Truncate unanchored sentences from end of body
    if section.body:
        sentences = _SENTENCE_SPLIT_PATTERN.split(section.body)
        kept_sentences = []
        for s in sentences:
            if re.search(r"\[pdf-\d+\]", s, re.IGNORECASE) or re.search(r"\[req-\d+\]", s, re.IGNORECASE):
                kept_sentences.append(s)
            else:
                temp_text = " ".join(kept_sentences + [s])
                temp_words = _count_words(temp_text)
                for b in section.bullets:
                    temp_words += _count_words(b.text)
                if temp_words <= budget:
                    kept_sentences.append(s)
                else:
                    modified = True
        section.body = " ".join(kept_sentences).strip()
        
    return modified
