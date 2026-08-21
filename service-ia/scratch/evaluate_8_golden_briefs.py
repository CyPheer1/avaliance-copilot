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
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
rfp_url = "http://localhost:8080/api/rfp/generate"

GOLDEN_BRIEFS = [
    {
        "id": 1,
        "name": "Santé / Portail Patient HDS & FHIR",
        "sector": "sante",
        "description": "Groupe hospitalier : déployer un portail patient sécurisé HDS, interopérable avec le Dossier Patient Informatisé (DPI) via des API REST et FHIR, et intégrant l'authentification ProSanté Connect.",
        "expected_evidence": True,
        "expected_doc": "05_Groupe_Santelia_Portail_Patient_Interoperabilite_Dossier_Projet.pdf",
    },
    {
        "id": 2,
        "name": "Cyber / Logistique NIS2 & SIEM",
        "sector": "logistique",
        "description": "Opérateur logistique : mise en conformité NIS2, gouvernance cyber, sécurisation du SI et segmentation réseau sur sites multiples.",
        "expected_evidence": True,
        "expected_doc": "03_TransAlpes_Logistique_Securisation_SI_NIS2_Rapport_Programme.pdf",
    },
    {
        "id": 3,
        "name": "Énergie / Socle IoT & Télérelève",
        "sector": "energie",
        "description": "Distributeur d'énergie : socle de collecte IoT et télérelève de compteurs communicants, ingestion temps réel et architecture distribuée.",
        "expected_evidence": True,
        "expected_doc": "04_Volteris_Energies_Socle_IoT_Telereleve_Dossier_Projet.pdf",
    },
    {
        "id": 4,
        "name": "Télécom / Data Platform & Churn",
        "sector": "telecom",
        "description": "Opérateur télécom : plateforme big data temps réel, calcul du churn et rétention client sur infrastructure cloud hybride.",
        "expected_evidence": True,
        "expected_doc": "02_Novacom_Telecom_Plateforme_Data_Retention_Bilan_Mission.pdf",
    },
    {
        "id": 5,
        "name": "Banque / NovaShield Sécurité",
        "sector": "banque",
        "description": "Banque de détail : refonte du socle de sécurité applicative NovaShield, authentification forte et protection des paiements.",
        "expected_evidence": True,
        "expected_doc": "01_Credalis_Banque_NovaShield_Bilan_Projet.pdf",
    },
    {
        "id": 6,
        "name": "Spatial / Crypto Quantique Nanosatellites (No Evidence)",
        "sector": "spatial",
        "description": "Agence spatiale : concevoir un système de cryptographie quantique embarquée pour constellation de nanosatellites en orbite basse (LEO) avec distribution de clés quantiques (QKD).",
        "expected_evidence": False,
        "expected_doc": None,
    },
    {
        "id": 7,
        "name": "Cuisine / Recette Tarte aux Pommes (No Evidence / Out of Scope)",
        "sector": "restauration",
        "description": "Recette de tarte aux pommes et pâtisserie artisanale au caramel beurre salé.",
        "expected_evidence": False,
        "expected_doc": None,
    },
    {
        "id": 8,
        "name": "Trivial / Salutation Seule (Rejet 400)",
        "sector": None,
        "description": "Bonjour !",
        "expected_evidence": False,
        "expected_status": 400,
    },
]

results = []
print("=================================================================")
print("EXECUTING 8-BRIEF GOLDEN SET EVALUATION")
print("=================================================================")

for item in GOLDEN_BRIEFS:
    b_id = item["id"]
    name = item["name"]
    desc = item["description"]
    sec = item.get("sector")
    exp_ev = item.get("expected_evidence", False)
    exp_doc = item.get("expected_doc")
    exp_status = item.get("expected_status", 200)

    print(f"\n--- Running Brief #{b_id}: {name} ---")
    t0 = time.time()
    try:
        resp = requests.post(rfp_url, json={"description": desc, "sector": sec, "topK": 5}, headers=headers, timeout=600)
        elapsed = round(time.time() - t0, 2)
        status = resp.status_code
        data = resp.json() if status == 200 else {}
    except Exception as e:
        elapsed = round(time.time() - t0, 2)
        status = 500
        data = {"error": str(e)}

    # Rubric Evaluation (100 pts)
    # 1. Brief Relevance & Needs Coverage (40 pts)
    # 2. 19-Section Completeness & Coherence (30 pts)
    # 3. Evidence & Citation Accuracy (30 pts)
    # Hallucination Penalty: -50 pts if irrelevant doc cited on no-evidence brief

    coverage_pts = 0
    section_pts = 0
    citation_pts = 0
    hallucination_penalty = 0

    if b_id == 8:
        # Rejection case (HTTP 400 or 422)
        if status in (400, 422):
            coverage_pts = 40
            section_pts = 30
            citation_pts = 30
            total_rubric = 100
        else:
            total_rubric = 0
        res_summary = {
            "id": b_id,
            "name": name,
            "status_code": status,
            "elapsed_s": elapsed,
            "rejection_handled": status in (400, 422),
            "rubric_score": total_rubric,
        }
        results.append(res_summary)
        print(f"Status: {status} (Expected: 400 or 422), Elapsed: {elapsed}s, Score: {total_rubric}/100")
        continue

    if status == 200:
        sections = data.get("proposal", {}).get("sections", [])
        sources = data.get("sources", [])
        ev_passed = data.get("evidenceValidationPassed", False)
        diagnostic = data.get("diagnostic")
        quality = data.get("quality", {})

        # Need coverage (40 pts)
        cov_score = quality.get("coverageScore", 1.0)
        coverage_pts = round(cov_score * 40, 1)

        # 19 sections completeness (30 pts)
        section_count = len(sections)
        section_pts = 30 if section_count == 19 else round((section_count / 19.0) * 30, 1)

        # Evidence & citation accuracy (30 pts)
        if exp_ev:
            # Must cite matching PDF
            matching_sources = [s for s in sources if exp_doc in (s.get("document_name") or "")]
            if matching_sources and ev_passed and diagnostic is None:
                citation_pts = 30
            elif sources:
                citation_pts = 15
            else:
                citation_pts = 0
        else:
            # Must cite NO PDF sources and have diagnostic NO_RELEVANT_PDF_EVIDENCE
            if len(sources) == 0 and not ev_passed and diagnostic == "NO_RELEVANT_PDF_EVIDENCE":
                citation_pts = 30
            else:
                # Hallucinated evidence!
                hallucination_penalty = -50
                citation_pts = 0

        total_rubric = max(0, min(100, int(coverage_pts + section_pts + citation_pts + hallucination_penalty)))

        res_summary = {
            "id": b_id,
            "name": name,
            "status_code": status,
            "elapsed_s": elapsed,
            "evidence_validation_passed": ev_passed,
            "diagnostic": diagnostic,
            "sources_count": len(sources),
            "citations_count": len(data.get("citations", [])),
            "similar_missions_count": len(data.get("similarMissions", [])),
            "section_count": section_count,
            "quality_report": quality,
            "rubric_breakdown": {
                "coverage_pts": f"{coverage_pts}/40",
                "structure_pts": f"{section_pts}/30",
                "citation_pts": f"{citation_pts}/30",
                "hallucination_penalty": hallucination_penalty,
                "total_rubric": f"{total_rubric}/100",
            },
        }
        results.append(res_summary)
        print(f"Status: {status}, Elapsed: {elapsed}s, Sections: {section_count}, Sources: {len(sources)}, Rubric: {total_rubric}/100")

print("\n=================================================================")
print("FINAL GOLDEN SET SCORING MATRIX")
print("=================================================================")
print(json.dumps(results, indent=2, ensure_ascii=False))

with open("service-ia/scratch/golden_set_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
