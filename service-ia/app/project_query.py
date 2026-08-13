"""Project-title extraction shared by retrieval and generation."""

from __future__ import annotations

import re
import unicodedata

_QUOTED_PROJECT_PATTERN = re.compile(r"[«\"]([^»\"]+)[»\"]")
_PROJECT_REFERENCE_PATTERN = re.compile(r"\b([A-Z]{2,10})[-_\s]?(\d{2,6})\b", re.IGNORECASE)
_UNQUOTED_PROJECT_PREFIX_PATTERNS = (
    re.compile(r"\bdans\s+le\s+projet\s+", re.IGNORECASE),
    re.compile(r"\b(?:du|de|au\s+sein\s+du|sur\s+le|concernant\s+le)\s+projet\s+", re.IGNORECASE),
    re.compile(r"\ble\s+projet\s+", re.IGNORECASE),
)
_PROJECT_QUERY_DELIMITER = re.compile(
    r"(?:,\s*|\s+[?.!]|\s+(?:qui|que|quel(?:le|les|s)?|comment|pourquoi|combien|où|quand|"
    r"est|a|a-t-il|a-t-elle|ont|ont-ils|ont-elles|faut-il|peut-on|doit-on|"
    r"quels\s+sont|quelles\s+sont)\b)",
    re.IGNORECASE,
)


def _looks_like_named_project(title: str) -> bool:
    stripped = title.strip(" ,")
    if not stripped:
        return False
    if not any(char.isupper() or char.isdigit() for char in stripped):
        return False
    return stripped.casefold() not in {"projet", "mission", "programme"}


def project_reference_from_query(query: str) -> str | None:
    """Return a normalized project reference such as AVA-012."""
    match = _PROJECT_REFERENCE_PATTERN.search(query)
    if match is None:
        return None
    return f"{match.group(1).upper()}-{match.group(2)}"


def project_title_from_query(query: str) -> str | None:
    """Return an explicitly named project title, including unquoted French queries."""
    match = _QUOTED_PROJECT_PATTERN.search(query)
    if match is not None:
        title = match.group(1).strip(" ,")
        return title or None

    for pattern in _UNQUOTED_PROJECT_PREFIX_PATTERNS:
        match = pattern.search(query)
        if match is None:
            continue
        candidate = query[match.end() :].strip()
        delimiter = _PROJECT_QUERY_DELIMITER.search(candidate)
        title = candidate[: delimiter.start()] if delimiter is not None else candidate
        title = title.strip(" ,?.!")
        if _looks_like_named_project(title):
            return title

    return project_reference_from_query(query)


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(character for character in decomposed if not unicodedata.combining(character)).casefold()


def project_terms(query: str) -> tuple[str, ...]:
    """Return identity terms from a project title, excluding programme labels."""
    title = project_title_from_query(query)
    if title is None:
        return ()
    # Programme codes can occur in document content but normally not every
    # page/chunk. The client/project title is the durable document identity.
    title = title.split("(", 1)[0]
    ignored = {"projet", "programme", "mission"}
    return tuple(
        term
        for term in re.findall(r"[a-z0-9]+", _fold(title))
        if len(term) >= 3 and term not in ignored
    )


def matches_named_project(query: str, *values: str | None) -> bool:
    """Whether all explicit project terms occur in supplied document evidence."""
    terms = project_terms(query)
    searchable = _fold(" ".join(value or "" for value in values))
    return bool(terms) and all(term in searchable for term in terms)