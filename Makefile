# =============================================================================
# Avaliance Copilot — Root Makefile
# =============================================================================
# Convenience targets for project management.
# Requires: Docker, Docker Compose, Python 3.11+, Maven (via wrapper).
# =============================================================================

.PHONY: up down ps logs infra test verify seed seed-db test-ia bench golden-rag eval-rag clean

ifeq ($(OS),Windows_NT)
PYTHON ?= py -3
MVNW ?= ./mvnw.cmd
else
PYTHON ?= python3
MVNW ?= sh ./mvnw
endif

# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

## Start infrastructure services (postgres + ollama)
infra:
	docker compose up -d postgres ollama

## Start all available services
up:
	docker compose up -d

## Stop all services
down:
	docker compose down

## Show service status
ps:
	docker compose ps

## Show service logs (follow mode)
logs:
	docker compose logs -f

# ---------------------------------------------------------------------------
# Development & Testing
# ---------------------------------------------------------------------------

## Run backend unit tests
test:
	cd backend && $(MVNW) test

## Run backend unit + integration tests
verify:
	cd backend && $(MVNW) verify

# ---------------------------------------------------------------------------
# Data & Corpus
# ---------------------------------------------------------------------------

## Generate synthetic corpus (300 missions, seed 42)
seed:
	$(PYTHON) data/generate_synthetic_corpus.py --mode templates --count 300 --seed 42 --output data/corpus

## Seed the database (ingest corpus via /ingest endpoint)
seed-db:
	$(PYTHON) scripts/seed_corpus.py --corpus-dir data/corpus --service-url http://localhost:8000

## Run service-ia (FastAPI) tests
test-ia:
	cd service-ia && $(PYTHON) -m pytest tests -q

# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

## Benchmark the configured Ollama generation model (CPU latency)
bench:
	$(PYTHON) scripts/benchmark_ollama.py --models $${LLM_MODEL:?set LLM_MODEL} --runs 3 --output benchmarks/ollama-cpu.json

## Export the strict 140-case machine-readable golden dataset
golden-rag:
	$(PYTHON) scripts/rag_golden.py Avaliance_Questions_Reponses_Claires.md benchmarks/rag-golden-v1.json

## Evaluate question 3 against every second golden RAG document (10 cases)
eval-rag: golden-rag
	$(PYTHON) scripts/evaluate_rag.py --golden Avaliance_Questions_Reponses_Claires.md --sample-project-step 2 --question-number 3 --output benchmarks/rag-sample-baseline.json

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

## Remove all volumes and containers
clean:
	docker compose down -v --remove-orphans
