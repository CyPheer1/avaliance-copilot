"""Avaliance Copilot — Internal IA Service (FastAPI).

Provides embedding, ingestion, retrieval and generation endpoints.
All endpoints require X-Internal-Token authentication.
"""

from __future__ import annotations

import json
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from .schemas import (
    EmbedRequest,
    EmbedResponse,
    GenerateRequest,
    GenerateResponse,
    IngestRequest,
    IngestResponse,
    RetrieveRequest,
    RetrieveResponse,
    RfpRequest,
    RfpResponse,
    SimilarRequest,
    SimilarResponse,
)
from .settings import Settings, get_settings

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Startup: load embedding model + init DB pool. Shutdown: cleanup."""
        from . import db, embeddings

        logger.info(
            "Starting service-ia with configured generation model=%s context=%s max_tokens=%s",
            resolved_settings.llm_model,
            resolved_settings.ollama_num_ctx,
            resolved_settings.generation_max_tokens,
        )

        # Initialise DB connection pool
        try:
            db.init_pool(resolved_settings.database_url)
            logger.info("Database pool initialised.")
        except Exception:
            logger.warning("Database pool init failed (DB may not be available). Continuing without DB.")

        # Load embedding model
        try:
            embeddings.load_model(resolved_settings.embedding_model_path)
            logger.info("Embedding model loaded.")
        except Exception:
            logger.warning("Embedding model load failed. /embed and /ingest will not work.")

        yield

        # Shutdown
        db.close_pool()
        logger.info("service-ia shutdown complete.")

    app = FastAPI(
        title="Avaliance Copilot IA",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    def require_internal_token(
        token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
    ) -> None:
        expected = resolved_settings.internal_token
        if token is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Internal token required")
        if not secrets.compare_digest(token, expected):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal token")

    # -----------------------------------------------------------------------
    # Health
    # -----------------------------------------------------------------------
    @app.get("/health", dependencies=[Depends(require_internal_token)])
    def health() -> dict[str, str]:
        from . import embeddings

        return {
            "status": "ok",
            "service": "service-ia",
            "embedding_model_loaded": str(embeddings.is_loaded()),
        }

    @app.get("/ready", dependencies=[Depends(require_internal_token)])
    def ready() -> dict[str, str]:
        from . import db, embeddings
        from .generation.ollama import is_configured_model_available

        if not db.is_initialized():
            raise HTTPException(status_code=503, detail="Database pool not initialized")
        if not embeddings.is_loaded():
            raise HTTPException(status_code=503, detail="Embedding model not loaded")
        if not is_configured_model_available(resolved_settings):
            raise HTTPException(
                status_code=503,
                detail=f"Configured Ollama model unavailable: {resolved_settings.llm_model}",
            )
        return {
            "status": "ready",
            "service": "service-ia",
            "llm_model": resolved_settings.llm_model,
        }

    # -----------------------------------------------------------------------
    # /embed — encode texts into vectors
    # -----------------------------------------------------------------------
    @app.post("/embed", dependencies=[Depends(require_internal_token)], response_model=EmbedResponse)
    def embed(request: EmbedRequest) -> EmbedResponse:
        from . import embeddings

        if not embeddings.is_loaded():
            raise HTTPException(status_code=503, detail="Embedding model not loaded")

        vectors = embeddings.encode(request.texts)

        return EmbedResponse(
            embeddings=[v.tolist() for v in vectors],
            dimension=embeddings.get_dimension(),
            count=len(vectors),
        )

    # -----------------------------------------------------------------------
    # /ingest — ingest missions into PostgreSQL with embeddings
    # -----------------------------------------------------------------------
    @app.post("/ingest", dependencies=[Depends(require_internal_token)], response_model=IngestResponse)
    def ingest(request: IngestRequest) -> IngestResponse:
        from .ingestion.pipeline import ingest_missions

        try:
            result = ingest_missions(
                missions=request.missions,
                chunk_max_characters=request.chunk_max_characters,
                chunk_overlap_characters=request.chunk_overlap_characters,
            )
        except RuntimeError as exc:
            if str(exc) == "Embedding model not loaded. Cannot ingest without embeddings.":
                raise HTTPException(status_code=503, detail="Embedding model not loaded") from exc
            raise
        return IngestResponse(**result)

    @app.post("/documents/ingest", dependencies=[Depends(require_internal_token)])
    async def ingest_document_file(
        document_id: Annotated[int, Form(gt=0)],
        file: Annotated[UploadFile, File()],
    ) -> dict[str, int]:
        from .ingestion.document_pipeline import ingest_document
        from .ingestion.extraction import DocumentExtractionError, UnsupportedDocumentError

        filename = file.filename or "document"
        try:
            await file.seek(0)
            data = await file.read()
            return ingest_document(document_id, filename, data)
        except UnsupportedDocumentError as exc:
            logger.warning("Document ingestion rejected document_id=%s filename=%r: %s", document_id, filename, exc)
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        except DocumentExtractionError as exc:
            logger.exception(
                "Document extraction failed document_id=%s filename=%r bytes=%s",
                document_id,
                filename,
                len(data) if "data" in locals() else None,
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            if str(exc) == "Embedding model not loaded. Cannot ingest without embeddings.":
                raise HTTPException(status_code=503, detail="Embedding model not loaded") from exc
            raise
        finally:
            await file.close()

    # -----------------------------------------------------------------------
    # /retrieve — vector search over indexed chunks
    # -----------------------------------------------------------------------
    @app.post("/retrieve", dependencies=[Depends(require_internal_token)], response_model=RetrieveResponse)
    def retrieve(request: RetrieveRequest) -> RetrieveResponse:
        from .retrieval.vector_search import vector_search

        try:
            return vector_search(request)
        except RuntimeError as exc:
            if str(exc) == "Embedding model not loaded. Call load_model() first.":
                raise HTTPException(status_code=503, detail="Embedding model not loaded") from exc
            raise

    @app.post("/retrieve/trace", dependencies=[Depends(require_internal_token)])
    def retrieve_trace(request: RetrieveRequest) -> dict[str, object]:
        """Expose an authenticated internal retrieval trace for reproducible evaluation."""
        from .retrieval.vector_search import vector_search_with_trace

        try:
            _, trace = vector_search_with_trace(request)
            return trace
        except RuntimeError as exc:
            if str(exc) == "Embedding model not loaded. Call load_model() first.":
                raise HTTPException(status_code=503, detail="Embedding model not loaded") from exc
            raise

    # -----------------------------------------------------------------------
    # /similar — missions ranked by semantic and technology-tag similarity
    # -----------------------------------------------------------------------
    @app.post("/similar", dependencies=[Depends(require_internal_token)], response_model=SimilarResponse)
    def similar(request: SimilarRequest) -> SimilarResponse:
        from .similar_missions.search import find_similar_missions

        try:
            return find_similar_missions(request)
        except RuntimeError as exc:
            if str(exc) == "Embedding model not loaded. Call load_model() first.":
                raise HTTPException(status_code=503, detail="Embedding model not loaded") from exc
            raise

    # -----------------------------------------------------------------------
    # /generate — sourced answer from retrieved chunks via local Ollama
    # -----------------------------------------------------------------------
    @app.post("/generate", dependencies=[Depends(require_internal_token)], response_model=GenerateResponse)
    def generate(request: GenerateRequest) -> GenerateResponse:
        from .generation.ollama import OllamaUnavailableError
        from .generation.service import generate_sourced_answer

        try:
            return generate_sourced_answer(request, resolved_settings)
        except OllamaUnavailableError as exc:
            raise HTTPException(status_code=503, detail="Ollama unavailable") from exc

    @app.get("/generation/diagnostics", dependencies=[Depends(require_internal_token)])
    def generation_diagnostics() -> dict[str, dict[str, int]]:
        """Aggregate failed grounding outcomes for evaluation and operations."""
        from .generation.service import grounding_diagnostic_counts

        return {"failedGrounding": grounding_diagnostic_counts()}

    # -----------------------------------------------------------------------
    # /generate/stream — SSE streaming of sourced answer tokens
    # -----------------------------------------------------------------------
    @app.post("/generate/stream", dependencies=[Depends(require_internal_token)])
    def generate_stream(request: GenerateRequest):
        from .generation.ollama import OllamaUnavailableError
        from .generation.service import generate_sourced_answer_stream

        logger.info("generate/stream request received query=%r", request.query)

        def stream_events():
            try:
                yield from generate_sourced_answer_stream(request, resolved_settings)
            except OllamaUnavailableError:
                logger.exception("Ollama became unavailable during generation stream")
                yield f"event: error\ndata: {json.dumps({'error': 'Ollama unavailable'})}\n\n"
            except GeneratorExit:
                logger.info("generate/stream client disconnected query=%r", request.query)
                raise
            except Exception:
                logger.exception("Generation stream failed")
                yield f"event: error\ndata: {json.dumps({'error': 'Generation stream failed'})}\n\n"
            finally:
                logger.info("generate/stream request finished query=%r", request.query)

        return StreamingResponse(
            stream_events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # -----------------------------------------------------------------------
    # /rfp — isolated PDF-evidence-first proposal workflow; synthetic missions are optional and labelled.
    # -----------------------------------------------------------------------
    @app.post("/rfp", dependencies=[Depends(require_internal_token)], response_model=RfpResponse)
    def rfp(request: RfpRequest) -> RfpResponse:
        from .generation.ollama import OllamaUnavailableError
        from .generation.service import generate_rfp_structure

        try:
            return generate_rfp_structure(request, resolved_settings)
        except OllamaUnavailableError as exc:
            raise HTTPException(status_code=503, detail="Ollama unavailable") from exc

    return app


app = create_app()