# Deployment modes

## NVIDIA GPU base deployment

The base Compose file assigns `gpus: all` to both Ollama and `service-ia`; it requires a host with the NVIDIA Container Toolkit configured. PostgreSQL, Ollama, and `service-ia` are private to the Docker network; only the Spring API (`8080`) and frontend (`3000`) are published.

```text
docker compose up -d --build
docker compose exec ollama ollama ps
docker compose exec service-ia python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

`ollama ps` must show the loaded model using GPU (for example, `100% GPU`). During a real generation request, use host `nvidia-smi` to verify VRAM and compute activity. The embedding loader selects CUDA when `torch.cuda.is_available()` and logs its selected device; inspect `service-ia` logs after startup to verify CUDA residency.

The optional `docker-compose.gpu.yml` repeats these declarations for compatibility with existing deployment commands; it is not required with the current base Compose file. Do not publish `5432`, `8000`, or `11434` in production. Use `docker compose exec` for maintenance operations that need those internal services.

## Required environment configuration

Copy `.env.example` to `.env`, replace all secret placeholders, and retain the non-secret generation defaults. Validate either mode before deploying:

```text
docker compose --env-file .env config --quiet
docker compose --env-file .env -f docker-compose.yml -f docker-compose.gpu.yml config --quiet
```

## Upgrade safety

This stack persists PostgreSQL, Ollama models, Hugging Face cache, and uploaded originals in named volumes. A rebuild does not reindex documents automatically. Apply Flyway migrations through the backend rollout, then use the administrator document reindex action only when a migration or ingestion change explicitly requires it.
