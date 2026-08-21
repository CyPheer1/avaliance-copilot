"""Test planner at max_tokens=1600 for clean completion."""

import json
import time
import httpx
from app.settings import get_settings
from app.generation.prompts import (
    RFP_PLANNER_PROMPT,
    RFP_PLANNER_SCHEMA,
)
from app.generation.rfp_proposal import RFP_19_SECTIONS

def strict_validate_json(raw: str):
    if "<think>" in raw.lower() or "</think>" in raw.lower():
        return False, "Contains <think> tags", None
    if "```" in raw:
        return False, "Contains markdown code fences", None
    stripped = raw.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return False, "Contains leading or trailing commentary outside JSON root", None
    try:
        parsed = json.loads(stripped)
        return True, "Valid strict JSON", parsed
    except Exception as e:
        return False, f"JSON parse error: {e}", None

def main():
    settings = get_settings()
    brief = "Groupe hospitalier régional : déployer un portail patient sécurisé conforme HDS."
    sources_str = "- [doc-01] 05_Groupe_Santelia.pdf (Page 1) : « Portail patient et interopérabilité DPI sécurisé HDS »"
    section_specs_str = "\n".join([f"{s['order']}. [{s['key']}] {s['title']} : {s['description']}" for s in RFP_19_SECTIONS])
    plan_prompt = RFP_PLANNER_PROMPT.format(
        brief=brief,
        atomic_needs='[{"id":"need-01","text":"Portail patient HDS"}]',
        sources=sources_str,
        section_specs=section_specs_str,
    )
    url = f"{settings.ollama_url.rstrip('/')}/api/generate"
    payload = {
        "model": settings.llm_model,
        "prompt": plan_prompt,
        "stream": False,
        "think": False,
        "keep_alive": settings.ollama_keep_alive,
        "format": RFP_PLANNER_SCHEMA,
        "options": {
            "temperature": 0,
            "num_predict": 1600,
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
    tps = eval_count / dur if dur > 0 else 0
    print("Planner at 1600 result:", {
        "duration_s": round(dur, 2),
        "prompt_tokens": prompt_eval,
        "output_tokens": eval_count,
        "tokens_per_sec": round(tps, 1),
        "is_valid_json": is_valid,
        "validation_reason": reason,
        "keys_count": len(parsed.get("plan", [])) if parsed and "plan" in parsed else 0,
    })

if __name__ == "__main__":
    main()
