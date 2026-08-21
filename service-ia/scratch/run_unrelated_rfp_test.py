import requests
import json
import time

env = {}
with open(".env", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")

admin_username = env.get("ADMIN_USERNAME", "admin")
admin_password = env.get("ADMIN_PASSWORD")

login_resp = requests.post("http://localhost:8080/api/auth/login", json={"username": admin_username, "password": admin_password}, timeout=10)
token = login_resp.json().get("token")

unrelated_brief = "Concevoir un système de cryptographie quantique embarquée pour constellation de nanosatellites en orbite basse (LEO) avec distribution de clés quantiques (QKD)."
rfp_url = "http://localhost:8080/api/rfp/generate"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}
payload = {
    "description": unrelated_brief,
    "sector": "spatial",
    "topK": 5
}

start_time = time.time()
resp = requests.post(rfp_url, json=payload, headers=headers, timeout=300)
elapsed = time.time() - start_time

data = resp.json()
proposal = data.get("proposal", {})
sections = proposal.get("sections", [])
sources = data.get("sources", [])
citations = data.get("citations", [])
quality = data.get("quality", {})
similar_missions = data.get("similarMissions", [])

# Check claim kinds
all_claims = []
for s in sections:
    all_claims.extend(s.get("claims", []))

kinds_found = set(c.get("kind") for c in all_claims if c.get("kind"))

result = {
    "http_status": resp.status_code,
    "elapsed_seconds": round(elapsed, 2),
    "evidence_validation_passed": data.get("evidenceValidationPassed"),
    "diagnostic": data.get("diagnostic"),
    "sources_count": len(sources),
    "citations_count": len(citations),
    "similar_missions_count": len(similar_missions),
    "section_count": len(sections),
    "claim_kinds_in_proposal": list(kinds_found),
    "quality_report": quality,
    "sample_section_1": sections[0] if sections else None
}

print(json.dumps(result, indent=2, ensure_ascii=False))
