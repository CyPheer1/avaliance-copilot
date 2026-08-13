"""Seed the database by sending corpus missions to the /ingest endpoint.

Reads JSON files from the corpus directory and POSTs them in batches
to the service-ia /ingest endpoint.

Usage:
    python scripts/seed_corpus.py --corpus-dir data/corpus --batch-size 10
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def load_missions(corpus_dir: Path) -> list[dict]:
    """Load all mission JSON files from the corpus directory."""
    missions = []
    for path in sorted(corpus_dir.glob("mission-*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        missions.append(data)
    return missions


def send_batch(
    missions: list[dict],
    service_url: str,
    internal_token: str,
    chunk_max_characters: int = 512,
    chunk_overlap_characters: int = 64,
) -> dict:
    """POST a batch of missions to /ingest."""
    payload = json.dumps({
        "missions": missions,
        "chunk_max_characters": chunk_max_characters,
        "chunk_overlap_characters": chunk_overlap_characters,
    }).encode("utf-8")

    request = Request(
        f"{service_url}/ingest",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Internal-Token": internal_token,
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=600) as response:
            return json.loads(response.read())
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  HTTP {e.code}: {body}", file=sys.stderr)
        raise
    except URLError as e:
        print(f"  Connection error: {e.reason}", file=sys.stderr)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=Path("data/corpus"))
    parser.add_argument("--service-url", default="http://localhost:8000")
    parser.add_argument("--internal-token", default=os.getenv("INTERNAL_TOKEN"))
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--chunk-max", type=int, default=512)
    parser.add_argument("--chunk-overlap", type=int, default=64)
    args = parser.parse_args()

    if not args.internal_token:
        parser.error("--internal-token or the INTERNAL_TOKEN environment variable is required")

    missions = load_missions(args.corpus_dir)
    if not missions:
        print(f"No mission files found in {args.corpus_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(missions)} missions from {args.corpus_dir}")

    total_missions = 0
    total_chunks = 0
    total_embeddings = 0
    start_time = time.time()

    for i in range(0, len(missions), args.batch_size):
        batch = missions[i : i + args.batch_size]
        batch_num = i // args.batch_size + 1
        total_batches = (len(missions) + args.batch_size - 1) // args.batch_size

        print(f"  Batch {batch_num}/{total_batches} ({len(batch)} missions)...", end=" ", flush=True)
        batch_start = time.time()

        result = send_batch(
            missions=batch,
            service_url=args.service_url,
            internal_token=args.internal_token,
            chunk_max_characters=args.chunk_max,
            chunk_overlap_characters=args.chunk_overlap,
        )

        batch_duration = time.time() - batch_start
        total_missions += result["missions_inserted"]
        total_chunks += result["chunks_inserted"]
        total_embeddings += result["chunks_with_embeddings"]

        print(f"done in {batch_duration:.1f}s "
              f"(+{result['missions_inserted']} missions, "
              f"+{result['chunks_inserted']} chunks)")

    total_duration = time.time() - start_time
    print(f"\nSeeding complete in {total_duration:.1f}s:")
    print(f"  Missions: {total_missions}")
    print(f"  Chunks:   {total_chunks}")
    print(f"  Embeddings: {total_embeddings}")


if __name__ == "__main__":
    main()
