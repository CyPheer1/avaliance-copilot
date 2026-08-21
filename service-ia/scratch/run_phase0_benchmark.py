"""Phase 0 Performance Benchmark script for Qwen3:8b on Ollama."""

import json
import re
import time
import httpx
from app.settings import get_settings
from app.generation.prompts import (
    RFP_BRIEF_EXTRACTION_PROMPT,
    RFP_BRIEF_SCHEMA,
    RFP_PLANNER_PROMPT,
    RFP_PLANNER_SCHEMA,
    RFP_SECTION_BATCH_PROMPT,
    RFP_SECTION_BATCH_SCHEMA,
)
from app.generation.rfp_proposal import RFP_19_SECTIONS

def strict_validate_json(raw: str) -> tuple[bool, str, dict | list | None]:
    """Strict JSON validation: reject <think>, code fences, commentary, multi-object."""
    if "<think>" in raw.lower() or "</think>" in raw.lower():
        return False, "Contains <think> tags", None
    if "```" in raw:
        return False, "Contains markdown code fences", None
    stripped = raw.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")) and not (stripped.startswith("[") and stripped.endswith("]")):
        return False, "Contains leading or trailing commentary outside JSON root", None
    try:
        parsed = json.loads(stripped)
        return True, "Valid strict JSON", parsed
    except Exception as e:
        return False, f"JSON parse error: {e}", None

def run_ollama_call(prompt: str, schema: dict, max_tokens: int, settings) -> dict:
    url = f"{settings.ollama_url.rstrip('/')}/api/generate"
    payload = {
        "model": settings.llm_model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "keep_alive": settings.ollama_keep_alive,
        "format": schema,
        "options": {
            "temperature": 0,
            "num_predict": max_tokens,
            "num_ctx": settings.ollama_num_ctx,
        },
    }
    t0 = time.perf_counter()
    with httpx.Client(timeout=httpx.Timeout(180.0, connect=5.0)) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    t1 = time.perf_counter()
    duration_s = t1 - t0
    response_text = data.get("response", "")
    is_valid, reason, parsed = strict_validate_json(response_text)
    eval_count = data.get("eval_count", 0)
    prompt_eval_count = data.get("prompt_eval_count", 0)
    eval_duration_ns = data.get("eval_duration", 0)
    eval_duration_s = eval_duration_ns / 1e9 if eval_duration_ns else duration_s
    tokens_per_sec = eval_count / eval_duration_s if eval_duration_s > 0 else 0.0

    return {
        "duration_s": round(duration_s, 2),
        "duration_ms": round(duration_s * 1000, 1),
        "prompt_tokens": prompt_eval_count,
        "output_tokens": eval_count,
        "tokens_per_sec": round(tokens_per_sec, 1),
        "is_valid_json": is_valid,
        "validation_reason": reason,
        "parsed": parsed,
        "response_len": len(response_text),
    }

def main():
    settings = get_settings()
    print(f"Running Phase 0 Benchmark with model={settings.llm_model} at {settings.ollama_url}...")

    representative_brief = (
        "Groupe hospitalier régional : concevoir et déployer un portail patient sécurisé conforme HDS, "
        "intégrant l'authentification ProSanté Connect, l'interopérabilité FHIR/HL7 avec le Dossier Patient Informatisé (DPI), "
        "la prise de rendez-vous en ligne et la restitution sécurisée des résultats d'analyses sous 4 heures."
    )

    # 1. Brief Extraction Benchmark (max_tokens=800)
    print("\n--- 1. Brief Extraction Call ---")
    ext_prompt = RFP_BRIEF_EXTRACTION_PROMPT.format(description=representative_brief)
    ext_res = run_ollama_call(ext_prompt, RFP_BRIEF_SCHEMA, max_tokens=800, settings=settings)
    print(f"Duration: {ext_res['duration_s']}s ({ext_res['duration_ms']}ms)")
    print(f"Input tokens: {ext_res['prompt_tokens']} | Output tokens: {ext_res['output_tokens']} | TPS: {ext_res['tokens_per_sec']}")
    print(f"JSON Validity: {ext_res['is_valid_json']} ({ext_res['validation_reason']})")

    # 2. Planner Benchmark (max_tokens=1200)
    print("\n--- 2. Planner Call ---")
    atomic_needs_str = json.dumps(ext_res["parsed"].get("atomic_needs", []) if ext_res["parsed"] else [], ensure_ascii=False, indent=2)
    sources_str = "- [doc-01] 05_Groupe_Santelia.pdf (Page 1) : « Portail patient et interopérabilité DPI sécurisé HDS »"
    section_specs_str = "\n".join([f"{s['order']}. [{s['key']}] {s['title']} : {s['description']}" for s in RFP_19_SECTIONS])
    plan_prompt = RFP_PLANNER_PROMPT.format(
        brief=representative_brief,
        atomic_needs=atomic_needs_str,
        sources=sources_str,
        section_specs=section_specs_str,
    )
    plan_res = run_ollama_call(plan_prompt, RFP_PLANNER_SCHEMA, max_tokens=1200, settings=settings)
    print(f"Duration: {plan_res['duration_s']}s ({plan_res['duration_ms']}ms)")
    print(f"Input tokens: {plan_res['prompt_tokens']} | Output tokens: {plan_res['output_tokens']} | TPS: {plan_res['tokens_per_sec']}")
    print(f"JSON Validity: {plan_res['is_valid_json']} ({plan_res['validation_reason']})")

    # 3. Writer Cluster Benchmark (Cluster 1: Sections 1-4, max_tokens=1500)
    print("\n--- 3. Writer Cluster Call (Cluster 1: Sections 1-4) ---")
    cluster_specs_str = "\n".join([f"{s['order']}. [{s['key']}] {s['title']} : {s['description']}" for s in RFP_19_SECTIONS[:4]])
    cluster_prompt = RFP_SECTION_BATCH_PROMPT.format(
        section_specs=cluster_specs_str,
        brief=representative_brief,
        sources=sources_str,
    )
    cluster_res = run_ollama_call(cluster_prompt, RFP_SECTION_BATCH_SCHEMA, max_tokens=1500, settings=settings)
    print(f"Duration: {cluster_res['duration_s']}s ({cluster_res['duration_ms']}ms)")
    print(f"Input tokens: {cluster_res['prompt_tokens']} | Output tokens: {cluster_res['output_tokens']} | TPS: {cluster_res['tokens_per_sec']}")
    print(f"JSON Validity: {cluster_res['is_valid_json']} ({cluster_res['validation_reason']})")

    # Projections
    t_ext = ext_res["duration_s"]
    t_plan = plan_res["duration_s"]
    t_clust = cluster_res["duration_s"]
    t_normal_7 = round(t_ext + t_plan + (5 * t_clust), 2)
    t_worst_8 = round(t_normal_7 + t_clust, 2)  # 1 repair call assumed ~ same as 1 cluster call

    print("\n=== BENCHMARK SUMMARY & PROJECTIONS ===")
    print(f"Extraction duration: {t_ext}s")
    print(f"Planner duration: {t_plan}s")
    print(f"Representative writer cluster duration: {t_clust}s")
    print(f"Normal 7-call pipeline projection (ext + plan + 5 clusters): {t_normal_7}s")
    print(f"Worst-case 8-call pipeline projection (normal + 1 targeted repair): {t_worst_8}s")
    print(f"Global deadline limit: 540.0s")
    print(f"Exceeds 540s limit? {'YES (OPTIMIZATION REQUIRED)' if t_normal_7 > 540 else 'NO (PROCEED)'}")

    # Output structured summary to scratch for reference
    summary = {
        "model": settings.llm_model,
        "extraction": ext_res,
        "planner": plan_res,
        "cluster": cluster_res,
        "projection_normal_7_calls_s": t_normal_7,
        "projection_worst_case_8_calls_s": t_worst_8,
        "global_deadline_s": 540.0,
    }
    # Do not save confidential data, just metrics
    summary_clean = {
        "model": settings.llm_model,
        "extraction": {k: v for k, v in ext_res.items() if k != "parsed"},
        "planner": {k: v for k, v in plan_res.items() if k != "parsed"},
        "cluster": {k: v for k, v in cluster_res.items() if k != "parsed"},
        "projection_normal_7_calls_s": t_normal_7,
        "projection_worst_case_8_calls_s": t_worst_8,
        "global_deadline_s": 540.0,
    }
    with open("/app/scratch/benchmark_phase0_results.json", "w") as f:
        json.dump(summary_clean, f, indent=2)

if __name__ == "__main__":
    main()
