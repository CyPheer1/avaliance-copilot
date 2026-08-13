from app.ingestion.chunking import chunk_text


def test_chunk_text_preserves_content_with_bounded_chunks():
    text = "alpha beta gamma delta epsilon zeta eta theta"

    chunks = chunk_text(text, max_characters=20, overlap_characters=6)

    assert chunks == [
        "alpha beta gamma",
        "delta epsilon zeta",
        "eta theta",
    ]
    assert all(len(chunk) <= 20 for chunk in chunks)


def test_chunk_text_normalizes_whitespace_and_rejects_empty_content():
    assert chunk_text("  alpha\n\n beta\t gamma  ", 20, 0) == ["alpha\n\nbeta gamma"]
    assert chunk_text("   \n\t ", 20, 0) == []


def test_chunk_text_preserves_paragraphs_and_overlaps_one_complete_sentence():
    text = (
        "Première phrase utile. Deuxième phrase détaillée.\n\n"
        "Troisième phrase courte. Quatrième phrase finale."
    )

    chunks = chunk_text(
        text,
        max_characters=90,
        overlap_characters=45,
        target_characters=80,
        min_characters=30,
    )

    assert "\n\n" in chunks[0]
    assert chunks[1].startswith("Troisième phrase courte.")
    assert all(len(chunk) <= 90 for chunk in chunks)


def test_chunk_text_caps_overlap_at_140_characters():
    long_sentence = "Une phrase complète " + "très longue " * 12 + "."
    text = long_sentence + " Une autre phrase suffisamment longue pour un second chunk."

    chunks = chunk_text(
        text,
        max_characters=180,
        overlap_characters=160,
        target_characters=150,
        min_characters=50,
    )

    assert len(chunks) == 2
    assert not chunks[1].startswith(long_sentence)
