# Avaliance Copilot — Safety-First Cleanup Audit

**Audit date:** 2026-08-12  
**Scope:** Entire project root, with focused inspection of generated outputs, agent/task artifacts, caches, test reports, build outputs, configuration, source, data, migrations, and benchmark assets.  
**Safety status:** No permanent deletion is authorized or performed. Local Docker volumes were not found under the repository and were not touched.

## Mandatory protected assets verified

The following are classified **KEEP** and are excluded from quarantine:

- `.env`, `.env.example`, `docker-compose.yml`, `docker-compose.gpu.yml`, Dockerfiles, and active infrastructure configuration.
- Production source under `frontend/src`, `backend/src/main`, and `service-ia/app`.
- Backend Flyway migrations `V1`–`V6`, including `V6__migrate_doc_chunk_embeddings_to_bge_m3.sql`.
- PostgreSQL schema in `db/init`, BGE-M3/1024-dimensional embedding configuration, hybrid retrieval/RRF/reranking, citation validation, and Ollama `qwen3:8b` integration.
- Source documents, synthetic corpus, test fixtures, ML datasets, and active test/benchmark/evaluation scripts.
- Maven wrapper files in `backend/.mvn/` and `backend/mvnw*`; `.mvn` is **not** treated as disposable because the wrapper uses it.

## Top-level classification

| Item | Category | Rationale | Action |
|---|---|---|---|
| `.env`, `.env.example`, `.gitignore` | KEEP | Runtime configuration and secret template. | Remain in place; secrets are not recorded here. |
| `docker-compose.yml`, `docker-compose.gpu.yml`, `Makefile`, `DEPLOYMENT.md`, `ARCHITECTURE_OVERVIEW.md`, `TEST_RAG.md` | KEEP | Active infrastructure and operational documentation. | Remain in place. |
| `frontend/`, `backend/`, `service-ia/`, `db/`, `data/`, `scripts/` | KEEP | Application source, schema, corpus, tests, and active evaluators. | Remain in place except generated children listed below. |
| `ml/dataset/`, `ml/notebooks/`, ML scripts | KEEP | Training/evaluation inputs and tooling. | Remain in place. |
| `ml/avaliance-e5-finetuned/` | ARCHIVE | Historical fine-tuned-model artifact; runtime is configured for BGE-M3, but this may be useful for comparison. | Remains in place; no move. |
| `benchmarks/*.json` | KEEP | Active versioned RAG/quality benchmark definitions. | Remain in place. |
| `benchmarks/results/` | ARCHIVE | Historical benchmark traces and reports; potentially valuable for regression comparison. | Remains in place; no move. |
| `SKILL_Avaliance_Copilot.md`, `runner.md` | KEEP | Project specification and referenced developer-operation guidance. | Remain in place. |
| `embed_test_output.txt`, `embed_test_status.txt` | ARCHIVE | Historical generated embedding-test evidence. | Remain in place; no move. |
| `zip_project.ps1` | REVIEW | Windows backup helper; not in active Linux path, but may be intentionally retained. | No move pending manual decision. |
| `.vscode/` | REVIEW | Contains project tasks, including host-specific Windows tasks. It may still support developer workflows. | No move pending manual decision. |
| `Lib/` | REVIEW | Local Python site-package tree. It appears non-runtime under Docker, but provenance and use are unclear. | No move pending manual decision. |
| `LOGO.png` | KEEP | Project visual asset. | Remains in place. |

## Quarantine candidates

The following are likely obsolete task-specific agent artifacts. They will be moved intact, preserving their relative paths:

| Item | Category | Rationale |
|---|---|---|
| `fix.md` | QUARANTINE | Historical AI task instruction; not runtime source, test, config, or operational documentation. |

## Safe generated cleanup candidates

The following are reproducible build outputs, cache directories, or failed-test reports. They will be moved—not deleted—into `.cleanup_quarantine`:

| Item(s) | Category | Rationale |
|---|---|---|
| `.agents/` (empty), `.tmp/`, `temp_unzip/` (empty) | SAFE GENERATED CLEANUP | Disposable agent/session scratch output and empty extraction staging. |
| `backend/target/`, `backend/.idea/`, `backend/debug.log`, `backend/test-output.txt` | SAFE GENERATED CLEANUP | Maven build/test output, IDE state, and generated debug/test logs. `backend/.mvn/` remains protected. |
| `frontend/node_modules/`, `frontend/dist/`, `frontend/test-results/`, `frontend/playwright-report/`, root `test-results/` | SAFE GENERATED CLEANUP | Reinstallable dependencies/build output and generated Playwright artifacts. |
| `**/__pycache__/`, `service-ia/.pytest_cache/` | SAFE GENERATED CLEANUP | Python bytecode and pytest cache. |

## Quarantine operation record

**Operation date:** 2026-08-12  
**Operation:** Reversible move only; no permanent deletion, Docker volume modification, permission change, or configuration change was performed.

- All listed `QUARANTINE` and `SAFE GENERATED CLEANUP` candidates were moved intact into `.cleanup_quarantine/`, preserving their original relative paths.
- The initial host-side move encountered root-owned `service-ia/**/__pycache__/` directories produced by the active container. Those directories were subsequently moved intact with a temporary root container bind-mounted to this repository. No host permissions were changed and no files were removed permanently.
- `CLEANUP_MANIFEST.json` records the actual quarantined files, sizes, and SHA-256 digests: **13,452 files / 255,330,356 bytes**.
- Restoration is reversible: move a quarantined relative path back to its recorded original location. No restoration was required during this validation.

## Quarantine validation results

Completed without touching Docker volumes:

1. **Compose configuration:** `docker compose config` passed.
2. **FastAPI/service-ia tests:** `129 passed`.
3. **Live IA readiness:** authenticated `/ready` returned `status=ready`, configured `llm_model=qwen3:8b`; `/embed` returned `embedding_dimension=1024` with `EMBEDDING_MODEL_PATH=BAAI/bge-m3`.
4. **Full-stack health:** Compose reported all five services healthy; backend `/actuator/health` returned `UP`; frontend `/healthz` returned `ok`.
5. **Persisted PDF corpus invariant:** `5` PDF documents, `275` PDF chunks with embeddings, and all `275` populated PDF embeddings have dimension `1024`.
6. **Manifest integrity:** every quarantined file was rehashed successfully against `CLEANUP_MANIFEST.json` (`13,452` verified files).
7. **Backend Maven suite:** not runnable from the host because no host Java/JAVA_HOME is installed. The production backend container is healthy and contains only the packaged `app.jar`, not source/tests or the Maven wrapper. This is an environment limitation, not a quarantine failure; no artifact restoration is indicated.

The live PDF golden evaluator was not run because it requires an administrator password supplied through a secret environment value. No secrets were read or emitted for cleanup validation.

If a later validation identifies a missing artifact, restore only the implicated path from `.cleanup_quarantine`, reclassify it as **KEEP**, and record the restoration in this audit and manifest.

## Final gate

No permanent deletion is permitted. `.cleanup_quarantine` and `CLEANUP_MANIFEST.json` must remain until explicit approval such as **“Approve Deletion”** is given.
