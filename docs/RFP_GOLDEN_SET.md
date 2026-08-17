# RFP Golden Evaluation Set (P0)

Ce référentiel contient les 8 briefs canoniques de test pour l'évaluation de la génération de propositions commerciales (RFP) selon la spécification P0 (100% PDF interne PostgreSQL/pgvector, isolation stricte des données synthétiques, composition en 19 sections).

---

## 1. Brief 1 — Santé : Portail Patient Sécurisé HDS & FHIR (Cas Preuve PDF Pertinente)
- **Secteur** : Santé
- **Brief** : « Groupe hospitalier : déployer un portail patient sécurisé HDS, interopérable avec le Dossier Patient Informatisé (DPI) via des API REST et FHIR, et intégrant l'authentification ProSanté Connect. »
- **Preuve PDF attendue** : `05_Groupe_Santelia_Portail_Patient_Interoperabilite_Dossier_Projet.pdf`
- **Résultat attendu** :
  - `evidence_validation_passed = true`
  - `diagnostic = null`
  - `sources` : Chunks issus du document Santélia Santé
  - 19 sections complètes respectant l'ordre canonique
  - `claims` : faits du brief typés `brief_fact`, références issues de Santélia typées `internal_evidence`
  - Score qualité >= 0.85

---

## 2. Brief 2 — Cyber & Conformité : Sécurisation SI & NIS2 (Cas Preuve PDF Pertinente)
- **Secteur** : Logistique / Cyber
- **Brief** : « Opérateur logistique : mise en conformité NIS2, gouvernance cyber, sécurisation du SI et segmentation réseau sur sites multiples. »
- **Preuve PDF attendue** : `03_TransAlpes_Logistique_Securisation_SI_NIS2_Rapport_Programme.pdf`
- **Résultat attendu** :
  - `evidence_validation_passed = true`
  - `diagnostic = null`
  - `sources` : Chunks issus du document TransAlpes NIS2
  - Citations précises avec numéros de page et extraits complets
  - Score qualité >= 0.85

---

## 3. Brief 3 — Énergie : Socle IoT & Télérelève (Cas Preuve PDF Pertinente)
- **Secteur** : Énergie
- **Brief** : « Distributeur d'énergie : socle de collecte IoT et télérelève de compteurs communicants, ingestion temps réel et architecture distribuée. »
- **Preuve PDF attendue** : `04_Volteris_Energies_Socle_IoT_Telereleve_Dossier_Projet.pdf`
- **Résultat attendu** :
  - `evidence_validation_passed = true`
  - `diagnostic = null`
  - `sources` : Chunks issus de Volteris Énergies
  - 19 sections structurées avec matrice de risques et livrables

---

## 4. Brief 4 — Télécom : Plateforme Data & Rétention (Cas Preuve PDF Pertinente)
- **Secteur** : Télécom
- **Brief** : « Opérateur télécom : plateforme big data temps réel, calcul du churn et rétention client sur infrastructure cloud hybride. »
- **Preuve PDF attendue** : `02_Novacom_Telecom_Plateforme_Data_Retention_Bilan_Mission.pdf`
- **Résultat attendu** :
  - `evidence_validation_passed = true`
  - `diagnostic = null`
  - `sources` : Chunks issus de Novacom Telecom
  - Citations exactes rattachées aux sections pertinentes

---

## 5. Brief 5 — Banque : NovaShield & Conformité Bancaire (Cas Preuve PDF Pertinente)
- **Secteur** : Banque
- **Brief** : « Banque de détail : refonte du socle de sécurité applicative NovaShield, authentification forte et protection des paiements. »
- **Preuve PDF attendue** : `01_Credalis_Banque_NovaShield_Bilan_Projet.pdf`
- **Résultat attendu** :
  - `evidence_validation_passed = true`
  - `sources` : Chunks issus de Credalis Banque
  - Score qualité >= 0.85

---

## 6. Brief 6 — Spatial : Cryptographie Quantique Nanosatellites (Cas AUCUNE Preuve PDF)
- **Secteur** : Spatial
- **Brief** : « Agence spatiale : concevoir un système de cryptographie quantique embarquée pour constellation de nanosatellites en orbite basse (LEO) avec distribution de clés quantiques (QKD). »
- **Preuve PDF attendue** : Aucune (aucun PDF spatial/quantique dans la base)
- **Résultat attendu** :
  - `evidence_validation_passed = false`
  - `diagnostic = "NO_RELEVANT_PDF_EVIDENCE"`
  - `sources = []` (aucun document logistique/santé/bancaire faussement cité)
  - `citations = []`
  - `similar_missions = []`
  - Proposition honnête basée sur les faits du brief, des recommandations méthodologiques, hypothèses et questions de cadrage
  - `quality.citation_integrity = 0.0` (signal clair et non trompeur)

---

## 7. Brief 7 — Restauration : Recette & Pâtisserie Artisanale (Cas Hors Sujet / Bruit Extrême)
- **Secteur** : Restauration
- **Brief** : « Recette de tarte aux pommes et pâtisserie artisanale au caramel beurre salé. »
- **Preuve PDF attendue** : Aucune
- **Résultat attendu** :
  - `evidence_validation_passed = false`
  - `diagnostic = "NO_RELEVANT_PDF_EVIDENCE"`
  - `sources = []`
  - Aucune hallucination de référence interne

---

## 8. Brief 8 — Input Trivial / Salutation Seule (Cas Rejet Immédiat)
- **Secteur** : Inconnu
- **Brief** : « Bonjour ! »
- **Résultat attendu** :
  - Rejet avec exception explicite (`RfpGenerationError` / HTTP 400 Bad Request)
  - Message explicite : « Le brief fourni ne contient aucun besoin exploitable pour construire une proposition. »

---

## Synthèse d'évaluation et Métriques P0

| N° | Brief | Domaine | Preuve attendue | Statut P0 | Diagnostic |
|---|---|---|---|---|---|
| 1 | Portail Patient HDS / FHIR | Santé | Santélia PDF | Pass (preuves citées) | `null` |
| 2 | Sécurisation SI & NIS2 | Cyber / Logistique | TransAlpes PDF | Pass (preuves citées) | `null` |
| 3 | Socle IoT & Télérelève | Énergie | Volteris PDF | Pass (preuves citées) | `null` |
| 4 | Data Retention & Churn | Télécom | Novacom PDF | Pass (preuves citées) | `null` |
| 5 | NovaShield Sécurité | Banque | Credalis PDF | Pass (preuves citées) | `null` |
| 6 | Crypto Quantique Spatial | Spatial | Aucune | Pass (repli honnête) | `NO_RELEVANT_PDF_EVIDENCE` |
| 7 | Tarte aux pommes | Cuisine / Bruit | Aucune | Pass (repli honnête) | `NO_RELEVANT_PDF_EVIDENCE` |
| 8 | Bonjour ! | Trivial | N/A | Rejet contrôlé (HTTP 400) | `EMPTY_OR_TRIVIAL_BRIEF` |
