import re


_DEFAULT_TARGET_CHARACTERS = 850
_DEFAULT_MIN_CHARACTERS = 250
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_PARAGRAPH_BOUNDARY = re.compile(r"\n\s*\n+")


def chunk_text(
    text: str,
    max_characters: int,
    overlap_characters: int,
    *,
    target_characters: int | None = None,
    min_characters: int | None = None,
) -> list[str]:
    if max_characters <= 0:
        raise ValueError("max_characters must be positive")
    if overlap_characters < 0 or overlap_characters >= max_characters:
        raise ValueError("overlap_characters must be between 0 and max_characters")

    target = target_characters or min(_DEFAULT_TARGET_CHARACTERS, max_characters)
    minimum = min_characters or min(_DEFAULT_MIN_CHARACTERS, target)
    if not 0 < minimum <= target <= max_characters:
        raise ValueError(
            "min_characters, target_characters and max_characters must be ordered"
        )

    paragraphs = [
        re.sub(r"\s+", " ", paragraph).strip()
        for paragraph in _PARAGRAPH_BOUNDARY.split(text.strip())
    ]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    if not paragraphs:
        return []

    units: list[tuple[str, int, bool]] = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        sentences = _SENTENCE_BOUNDARY.split(paragraph)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= max_characters:
                units.append((sentence, paragraph_index, True))
                continue
            parts = _split_oversized_words(sentence.split(" "), max_characters)
            units.extend(
                (part, paragraph_index, False)
                for part in parts
            )

    chunks: list[str] = []
    current: list[tuple[str, int, bool]] = []

    for unit in units:
        candidate = [*current, unit]
        candidate_length = len(_render_units(candidate))
        current_length = len(_render_units(current))
        should_append = (
            not current
            or candidate_length <= target
            or (current_length < minimum and candidate_length <= max_characters)
            or (
                current_length < target
                and candidate_length <= max_characters
                and abs(candidate_length - target) <= abs(current_length - target)
            )
        )
        if should_append:
            current = candidate
            continue

        chunks.append(_render_units(current))
        current = _overlap_sentence(current, overlap_characters)
        candidate = [*current, unit]
        current = candidate if len(_render_units(candidate)) <= max_characters else [unit]

    if current:
        chunks.append(_render_units(current))
    return chunks


def _render_units(units: list[tuple[str, int, bool]]) -> str:
    if not units:
        return ""
    rendered = units[0][0]
    for previous, current in zip(units, units[1:]):
        separator = "\n\n" if previous[1] != current[1] else " "
        rendered += separator + current[0]
    return rendered


def _overlap_sentence(
    units: list[tuple[str, int, bool]], overlap_characters: int
) -> list[tuple[str, int, bool]]:
    if not units or overlap_characters == 0:
        return []
    sentence = units[-1]
    if not sentence[2] or len(sentence[0]) > min(overlap_characters, 140):
        return []
    return [sentence]


def _split_oversized_words(words: list[str], max_characters: int) -> list[str]:
    result: list[str] = []
    current: list[str] = []
    for word in words:
        if len(word) > max_characters:
            if current:
                result.append(" ".join(current))
                current = []
            result.extend(
                word[index : index + max_characters]
                for index in range(0, len(word), max_characters)
            )
            continue
        candidate = " ".join([*current, word])
        if current and len(candidate) > max_characters:
            result.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        result.append(" ".join(current))
    return result
