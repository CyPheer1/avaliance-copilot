"""Validate a live-PDF golden suite against the current PostgreSQL corpus."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import psycopg2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("suite", type=Path)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "postgresql://copilot:change_me_db_password@localhost:5432/avaliance"))
    args = parser.parse_args()

    payload = json.loads(args.suite.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 2
    case_ids = [case["case_id"] for case in payload["cases"]]
    assert len(case_ids) == len(set(case_ids)), "duplicate case_id"

    connection = psycopg2.connect(args.database_url)
    try:
        with connection.cursor() as cursor:
            for case in payload["cases"]:
                for evidence in case["expected_evidence"]:
                    cursor.execute(
                        """
                        SELECT dc.source_document_id, sd.original_filename, sd.sha256,
                               dc.source_page, dc.chunk_index, dc.content
                        FROM doc_chunk dc
                        JOIN source_document sd ON sd.id = dc.source_document_id
                        WHERE dc.id = %s AND dc.corpus_scope = 'PDF'
                        """,
                        (evidence["chunk_id"],),
                    )
                    row = cursor.fetchone()
                    assert row is not None, f"missing PDF chunk {evidence['chunk_id']}"
                    document_id, filename, sha256, page, chunk_index, content = row
                    assert document_id == evidence["document_id"], evidence
                    assert filename == evidence["document_name"], evidence
                    assert sha256 == evidence["document_sha256"], evidence
                    assert page == evidence["page"], evidence
                    assert chunk_index == evidence["chunk_index"], evidence
                    assert evidence["evidence_quote"] in content, evidence
    finally:
        connection.close()

    print(f"Validated {len(payload['cases'])} cases and {sum(len(case['expected_evidence']) for case in payload['cases'])} evidence spans: {args.suite}")


if __name__ == "__main__":
    main()
