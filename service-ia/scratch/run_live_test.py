"""Live test runner against Spring Boot backend (http://localhost:8080)."""

import json
import time
import requests

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

print("1. Authenticating with Spring Boot...")
login_resp = requests.post(
    "http://localhost:8080/api/auth/login",
    json={"username": admin_username, "password": admin_password},
    timeout=10,
)
if login_resp.status_code != 200:
    print("Authentication failed:", login_resp.text)
    exit(1)

token = login_resp.json().get("token")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
rfp_url = "http://localhost:8080/api/rfp/generate"
print(f"2. Logged in successfully. Token length={len(token)}")

# -----------------------------------------------------------------------------
# TEST 1: Live Brief 1 (Relevant PDF Evidence)
# -----------------------------------------------------------------------------
print("\n" + "=" * 60)
print("TEST 1: Live Brief 1 — Santé / Portail Patient HDS & FHIR")
print("=" * 60)
brief1_payload = {
    "description": "Groupe hospitalier : déployer un portail patient sécurisé HDS, interopérable avec le Dossier Patient Informatisé (DPI) via des API REST et FHIR, et intégrant l'authentification ProSanté Connect.",
    "sector": "sante",
    "topK": 5,
}

t0 = time.time()
resp1 = requests.post(rfp_url, json=brief1_payload, headers=headers, timeout=600)
elapsed1 = round(time.time() - t0, 2)
print(f"Status Code: {resp1.status_code}, Elapsed: {elapsed1}s")

if resp1.status_code == 200:
    data1 = resp1.json()
    with open("service-ia/scratch/live_brief1_response.json", "w", encoding="utf-8") as f:
        json.dump(data1, f, indent=2, ensure_ascii=False)

    proposal = data1.get("proposal", {})
    sections = proposal.get("sections", [])
    sources = data1.get("sources", [])
    citations = data1.get("citations", [])
    quality = data1.get("quality", {})
    cluster_metrics = data1.get("clusterMetrics", [])

    print(f"Proposal Title: {proposal.get('title')}")
    exec_sum = proposal.get('executive_summary') or proposal.get('executiveSummary') or ''
    print(f"Executive Summary: {exec_sum[:120]}...")
    print(f"Sections Count: {len(sections)} / 19")
    print(f"Evidence Validation Passed: {data1.get('evidenceValidationPassed')}")
    print(f"Sources Count: {len(sources)}")
    print(f"Citations Count: {len(citations)}")
    print(f"Quality Score: {quality.get('score')} (Passed: {quality.get('passed')})")
    print(f"Generation Mode: {quality.get('generationMode')}")
    print(f"Warnings ({len(quality.get('warnings', []))}): {quality.get('warnings')}")
    print(f"Cluster Metrics Count: {len(cluster_metrics)}")
else:
    print("Error:", resp1.text)

# -----------------------------------------------------------------------------
# TEST 2: Live Brief 6 (No Evidence Honest Fallback)
# -----------------------------------------------------------------------------
print("\n" + "=" * 60)
print("TEST 2: Live Brief 6 — Spatial / Crypto Quantique (No PDF Evidence)")
print("=" * 60)
brief6_payload = {
    "description": "Agence spatiale : concevoir un système de cryptographie quantique embarquée pour constellation de nanosatellites en orbite basse (LEO) avec distribution de clés quantiques (QKD).",
    "sector": "spatial",
    "topK": 5,
}

t0 = time.time()
resp6 = requests.post(rfp_url, json=brief6_payload, headers=headers, timeout=600)
elapsed6 = round(time.time() - t0, 2)
print(f"Status Code: {resp6.status_code}, Elapsed: {elapsed6}s")

if resp6.status_code == 200:
    data6 = resp6.json()
    with open("service-ia/scratch/live_brief6_no_evidence_response.json", "w", encoding="utf-8") as f:
        json.dump(data6, f, indent=2, ensure_ascii=False)

    quality6 = data6.get("quality", {})
    print(f"Sections Count: {len(data6.get('proposal', {}).get('sections', []))} / 19")
    print(f"Evidence Validation Passed: {data6.get('evidenceValidationPassed')}")
    print(f"Diagnostic: {data6.get('diagnostic')}")
    print(f"Sources Count: {len(data6.get('sources', []))}")
    print(f"Quality Score: {quality6.get('score')} (Score Ceiling <= 0.70 applied: {quality6.get('score', 1.0) <= 0.70})")
    print(f"Warnings ({len(quality6.get('warnings', []))}): {quality6.get('warnings')}")
else:
    print("Error:", resp6.text)

# -----------------------------------------------------------------------------
# TEST 3: Live Brief 8 (Trivial Greeting 400/422 Rejection)
# -----------------------------------------------------------------------------
print("\n" + "=" * 60)
print("TEST 3: Live Brief 8 — Trivial Greeting ('Bonjour !') Rejection")
print("=" * 60)
brief8_payload = {
    "description": "Bonjour !",
}

t0 = time.time()
resp8 = requests.post(rfp_url, json=brief8_payload, headers=headers, timeout=10)
elapsed8 = round(time.time() - t0, 2)
print(f"Status Code: {resp8.status_code} (Expected: 400), Elapsed: {elapsed8}s")
print(f"Response Body: {resp8.text}")
print("Rejection Handled Correctly:", resp8.status_code in (400, 422))
