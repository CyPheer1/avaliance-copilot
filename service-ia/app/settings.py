from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    internal_token: str = Field(min_length=16)
    database_url: str = Field(default="postgresql://copilot:change_me_db_password@postgres:5432/avaliance")
    embedding_model_path: str = Field(default="BAAI/bge-m3")
    ollama_url: str = Field(default="http://ollama:11434")
    llm_model: str = Field(min_length=1)
    ollama_timeout_seconds: float = Field(default=180.0, gt=0)
    ollama_num_ctx: int = Field(default=8192, ge=512, le=32768)
    generation_max_tokens: int = Field(default=1500, ge=32, le=2048)
    generation_max_context_chunks: int = Field(default=20, ge=1, le=30)
    generation_cache_max_entries: int = Field(default=256, ge=0, le=4096)
    ollama_keep_alive: str = Field(default="10m", min_length=1)
    contextual_retrieval_enabled: bool = Field(default=True)
    contextual_retrieval_max_tokens: int = Field(default=120, ge=50, le=160)
    min_source_similarity: float = Field(default=0.55, ge=0.0, le=1.0)
    retrieval_candidate_limit: int = Field(default=50, ge=10, le=200)
    retrieval_rerank_limit: int = Field(default=30, ge=1, le=200)
    retrieval_rrf_k: int = Field(default=60, ge=1, le=1000)
    retrieval_vector_weight: float = Field(default=1.0, gt=0, le=10)
    retrieval_text_weight: float = Field(default=1.0, gt=0, le=10)
    retrieval_hnsw_ef_search: int = Field(default=100, ge=1, le=1000)
    retrieval_hnsw_iterative_scan: str = Field(default="strict_order", pattern="^(off|strict_order|relaxed_order)$")
    retrieval_rerank_lexical_bonus: float = Field(default=0.0, ge=0.0, le=2.0)
    retrieval_lexical_evidence_reserve: int = Field(default=5, ge=0, le=30)
    retrieval_evidence_rank_safeguard: int = Field(default=10, ge=0, le=100)
    retrieval_min_final_chunks: int = Field(default=10, ge=1, le=30)
    retrieval_max_final_chunks: int = Field(default=15, ge=1, le=30)


@lru_cache
def get_settings() -> Settings:
    return Settings()