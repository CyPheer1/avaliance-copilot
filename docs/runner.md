cd C:\Users\ordik\OneDrive\Documents\avaliance-copilot

# غير أول مرة
Copy-Item .env.example .env
# بدّل change_me_* داخل .env

docker compose up -d postgres ollama
# Pull the model selected by LLM_MODEL (qwen3:8b in .env.example).
docker compose exec ollama ollama pull qwen3:8b

# تشغيل المشروع كامل
docker compose up -d --build

# التحقق
docker compose ps

http://localhost:3000


cd frontend
npm run dev
cmd.exe /c npm run dev

## Évaluation RAG golden

Le stack doit être démarré et `.env` doit contenir `ADMIN_PASSWORD`.

```powershell
.\scripts\evaluate-rag.cmd
```

La commande valide et exporte les 140 cas dans `benchmarks/rag-golden-v1.json`,
puis teste la question 3 sur un PDF sur deux (10 requêtes) et écrit les résultats
dans `benchmarks/rag-sample-baseline.json`.
Sur un environnement disposant de GNU Make, la commande équivalente est
`make eval-rag`.


ssh -i "C:\aws\Documents_Aval-key.pem" ubuntu@13.48.135.13







Upgrade the Avaliance Copilot RAG system for fast, complete, accurate French answers from indexed PDFs, with true professional SSE token streaming.

Retrieval: retain PostgreSQL pgvector + French FTS RRF, but retrieve 50–100 candidates per branch, merge them, then rerank with GPU FP16 BAAI/bge-reranker-v2-m3. Select 6–10 diverse evidence chunks using relevance plus coverage across requested subtopics, pages, and documents. Remove hard truncation to three chunks and avoid unconditional adjacent-chunk concatenation. Tune filtered HNSW recall with per-query SET LOCAL hnsw.ef_search, and enable iterative scans when supported.

Generation: split the current strict quote extraction from user-facing answer synthesis. Internally validate exact evidence spans; externally generate a concise but complete professional French Markdown answer strictly from validated evidence, with inline [n] citations after factual claims. Return a reliable abstention if evidence is insufficient. Validate that citations map to selected chunks and reject unsupported citations/claims.

Streaming: replace fake post-generation chunking with direct async streaming from Ollama via the existing generate_text_stream() capability. Use SSE events: status, citations, delta, heartbeat, done, error. Emit citations before deltas, emit only real model tokens as delta, and never send done: true in an error event. Propagate cancellation from React AbortController through Spring WebFlux to FastAPI and close the Ollama stream. Buffer React state updates with requestAnimationFrame; add cancel and retry UX.

PDF ingestion: preserve headings, pages, tables/lists, and stable source offsets in chunk metadata. Explicitly keep OCR out of scope while documenting scanned-PDF limitations.

Configuration/model: `LLM_MODEL` is the sole generation-model setting. The selected and validated model is `qwen3:8b`; benchmark any future candidate on the Tesla T4 using real indexed PDFs and compare grounded-answer quality, TTFT, tokens/sec, total latency, and VRAM headroom. Do not adopt a 24B model by default on a 16 GB T4. `llama3.2:3b` is a retired migration baseline, not a runtime fallback.

Tests/evaluation: add real-PDF golden cases with expected evidence pages/chunks. Add regression tests for hybrid recall, reranking, citation correctness, abstention, SSE event order/error semantics, cancellation, TTFT, and streaming first-token behavior.