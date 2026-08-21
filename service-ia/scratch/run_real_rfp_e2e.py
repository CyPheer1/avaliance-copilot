import requests
import time
import json
import re

# Read .env file directly without external packages
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

print(f"Logging in to Spring Boot as '{admin_username}'...")
login_url = "http://localhost:8080/api/auth/login"
login_resp = requests.post(login_url, json={"username": admin_username, "password": admin_password}, timeout=10)

if login_resp.status_code != 200:
    print(f"Login failed: {login_resp.status_code} {login_resp.text}")
    exit(1)

token = login_resp.json().get("token")
print("Spring Boot login successful! Token obtained.")

# 2. Call /api/rfp/generate with real relevant brief
brief = "Groupe hospitalier : déployer un portail patient sécurisé HDS, interopérable avec le Dossier Patient Informatisé (DPI) via des API REST et FHIR, et intégrant l'authentification ProSanté Connect."
rfp_url = "http://localhost:8080/api/rfp/generate"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}
payload = {
    "description": brief,
    "sector": "sante",
    "topK": 5
}

print(f"Sending real RFP generation request for brief: '{brief}'...")
start_time = time.time()
rfp_resp = requests.post(rfp_url, json=payload, headers=headers, timeout=300)
elapsed = time.time() - start_time

print(f"\n==========================================")
print(f"RFP Response Status: {rfp_resp.status_code}")
print(f"Total Execution Time: {elapsed:.2f} seconds")
print(f"==========================================\n")

if rfp_resp.status_code != 200:
    print(f"Error from RFP generation: {rfp_resp.text}")
    exit(1)

data = rfp_resp.json()

# Save complete sanitized result for auditing
with open("/home/ubuntu/apps/avaliance-copilot/service-ia/scratch/real_rfp_result.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

proposal = data.get("proposal", {})
sections = proposal.get("sections", [])
sources = data.get("sources", [])
citations = data.get("citations", [])
quality = data.get("quality", {})
similar_missions = data.get("similarMissions", [])

# Extract verified internal evidence claims
evidence_claims = []
for sec in sections:
    for ref in sec.get("verifiedReferences", []):
        evidence_claims.append({
            "section_key": sec.get("key"),
            "section_title": sec.get("title"),
            "claim_text": ref.get("text"),
            "citation_indexes": ref.get("citationIndexes", [])
        })

summary = {
    "http_status": rfp_resp.status_code,
    "elapsed_seconds": round(elapsed, 2),
    "section_count": len(sections),
    "section_keys_in_order": [s.get("key") for s in sections],
    "section_statuses": [{s.get("key"): s.get("status")} for s in sections],
    "quality_report": quality,
    "diagnostic": data.get("diagnostic"),
    "evidence_validation_passed": data.get("evidenceValidationPassed"),
    "sources_count": len(sources),
    "citations_count": len(citations),
    "similar_missions_count": len(similar_missions),
    "sources_registry": sources,
    "evidence_claims": evidence_claims,
    "first_3_sections": [
        {
            "key": s.get("key"),
            "title": s.get("title"),
            "status": s.get("status"),
            "narrative_count": len(s.get("narrative", [])),
            "recommendations_count": len(s.get("recommendations", [])),
            "tables_count": len(s.get("tables", [])),
            "verified_references": s.get("verifiedReferences", [])
        }
        for s in sections[:3]
    ]
}

print(json.dumps(summary, indent=2, ensure_ascii=False))
