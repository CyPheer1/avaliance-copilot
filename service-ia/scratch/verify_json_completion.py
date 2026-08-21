"""Verify full JSON completion with adjusted token budgets."""

import json
import time
import httpx
from app.settings import get_settings
from app.generation.prompts import (
    RFP_PLANNER_PROMPT,
    RFP_PLANNER_SCHEMA,
    RFP_SECTION_BATCH_PROMPT,
    RFP_SECTION_BATCH_SCHEMA,
)
from app.generation.rfp_proposal import RFP_19_SECTIONS

def strict_validate_json(raw: str) -> tuple[bool, str, dict | list | None]:
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

def run_call(prompt: str, schema: dict, max_tokens: int, settings):
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
    dur = t1 - t0
    resp_text = data.get("response", "")
    is_valid, reason, parsed = strict_validate_json(resp_text)
    eval_count = data.get("eval_count", 0)
    prompt_eval = data.get("prompt_eval_count", 0)
    tps = eval_count / (dur) if dur > 0 else 0
    return {
        "duration_s": round(dur, 2),
        "prompt_tokens": prompt_eval,
        "output_tokens": eval_count,
        "tokens_per_sec": round(tps, 1),
        "is_valid_json": is_valid,
        "validation_reason": reason,
        "keys_count": len(parsed.get("plan", [])) if parsed and "plan" in parsed else (len(parsed.get("sections", [])) if parsed and "sections" in parsed else 0),
    }

def main():
    settings = get_settings()
    brief = "Groupe hospitalier régional : déployer un portail patient sécurisé conforme HDS."
    sources_str = "- [doc-01] 05_Groupe_Santelia.pdf (Page 1) : « Portail patient et interopérabilité DPI sécurisé HDS »"
    
    print("Testing Planner at max_tokens=1400...")
    section_specs_str = "\n".join([f"{s['order']}. [{s['key']}] {s['title']} : {s['description']}" for s in RFP_19_SECTIONS])
    plan_prompt = RFP_PLANNER_PROMPT.format(
        brief=brief,
        atomic_needs='[{"id":"need-01","text":"Portail patient HDS"}]',
        sources=sources_str,
        section_specs=section_specs_str,
    )
    plan_res = run_call(plan_prompt, RFP_PLANNER_SCHEMA, max_tokens=1400, settings=settings)
    print("Planner result:", plan_res)

    print("\nTesting Writer Cluster 1 at max_tokens=1800...")
    cluster_specs_str = "\n".join([f"{s['order']}. [{s['key']}] {s['title']} : {s['description']}" for s in RFP_19_SECTIONS[:4]])
    cluster_prompt = RFP_SECTION_BATCH_PROMPT.format(
        section_specs=cluster_specs_str,
        brief=brief,
        sources=sources_str,
    )
    clust_res = run_call(cluster_prompt, RFP_SECTION_BATCH_SCHEMA, max_tokens=1800, settings=settings)
    print("Cluster result:", clust_res)

if __name__ == "__main__":
    main()
