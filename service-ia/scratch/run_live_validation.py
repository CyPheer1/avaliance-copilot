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

# 1. Login
login_resp = requests.post("http://localhost:8080/api/auth/login", json={"username": admin_username, "password": admin_password}, timeout=10)
token = login_resp.json().get("token")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
rfp_url = "http://localhost:8080/api/rfp/generate"

print("=================================================================")
print("RUNNING REAL TEST 1: RELEVANT PDF (Santélia Santé HDS/FHIR)")
print("=================================================================")
brief_relevant = "Groupe hospitalier : déployer un portail patient sécurisé HDS, interopérable avec le Dossier Patient Informatisé (DPI) via des API REST et FHIR, et intégrant l'authentification ProSanté Connect."
t0 = time.time()
resp_rel = requests.post(rfp_url, json={"description": brief_relevant, "sector": "sante", "topK": 5}, headers=headers, timeout=600)
t_rel = time.time() - t0
print(f"Status Code: {resp_rel.status_code}, Elapsed: {t_rel:.2f}s")
data_rel = resp_rel.json()

summary_rel = {
    "http_status": resp_rel.status_code,
    "elapsed_seconds": round(t_rel, 2),
    "evidence_validation_passed": data_rel.get("evidenceValidationPassed"),
    "diagnostic": data_rel.get("diagnostic"),
    "sources_count": len(data_rel.get("sources", [])),
    "citations_count": len(data_rel.get("citations", [])),
    "similar_missions_count": len(data_rel.get("similarMissions", [])),
    "section_count": len(data_rel.get("proposal", {}).get("sections", [])),
    "sources": [
        {"id": s.get("id"), "title": s.get("title"), "document_name": s.get("document_name"), "page": s.get("page"), "chunk_id": s.get("chunk_id")}
        for s in data_rel.get("sources", [])
    ],
    "quality": data_rel.get("quality"),
}
print(json.dumps(summary_rel, indent=2, ensure_ascii=False))

print("\n=================================================================")
print("RUNNING REAL TEST 2: NO RELEVANT PDF (Quantum Cryptography LEO)")
print("=================================================================")
brief_unrel = "Agence spatiale : concevoir un système de cryptographie quantique embarquée pour constellation de nanosatellites en orbite basse (LEO) avec distribution de clés quantiques (QKD)."
t0 = time.time()
resp_unrel = requests.post(rfp_url, json={"description": brief_unrel, "sector": "spatial", "topK": 5}, headers=headers, timeout=600)
t_unrel = time.time() - t0
print(f"Status Code: {resp_unrel.status_code}, Elapsed: {t_unrel:.2f}s")
data_unrel = resp_unrel.json()

summary_unrel = {
    "http_status": resp_unrel.status_code,
    "elapsed_seconds": round(t_unrel, 2),
    "evidence_validation_passed": data_unrel.get("evidenceValidationPassed"),
    "diagnostic": data_unrel.get("diagnostic"),
    "sources_count": len(data_unrel.get("sources", [])),
    "citations_count": len(data_unrel.get("citations", [])),
    "similar_missions_count": len(data_unrel.get("similarMissions", [])),
    "section_count": len(data_unrel.get("proposal", {}).get("sections", [])),
    "quality": data_unrel.get("quality"),
}
print(json.dumps(summary_unrel, indent=2, ensure_ascii=False))
