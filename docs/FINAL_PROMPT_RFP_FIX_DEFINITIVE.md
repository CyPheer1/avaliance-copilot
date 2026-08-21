# MISSION FINALE — RÉPARATION DÉFINITIVE DU PARCOURS RFP AVALIANCE COPILOT

Tu es l’AI Coding Agent responsable de corriger réellement le projet Avaliance Copilot. Tu dois travailler directement dans le projet ouvert dans VS Code, après avoir identifié sa racine. Le backup de référence est `avaliance_copilot_backup_final.zip`.

**Ne t’arrête pas après l’audit.** Tu dois modifier le code, écrire les migrations et les tests, exécuter les validations, corriger chaque échec, puis fournir un rapport avec les preuves exactes. Tu ne dois jamais présenter un fallback, un mock ou une réponse partielle comme une réussite de production.

Le résultat attendu est un parcours RFP réellement cohérent et exploitable pour les vrais PDF uploadés sur la plateforme.

---

## 1. RÈGLES ABSOLUES DE SÉCURITÉ ET DE SCOPE

Ne touche pas aux ressources V8 suivantes et ne lance aucune opération destructive sur AWS :

```text
Compose project: avaliance-copilot
Directory: /home/ubuntu/apps/avaliance-copilot/
Containers: avaliance_backend, avaliance_frontend, avaliance_service_ia,
            avaliance_postgres, avaliance_ollama
Volumes: avaliance_pgdata, avaliance_ollama_models,
         avaliance_huggingface_cache, avaliance_document_storage
Network: avaliance-internal
Ports: 8080, 3000
```

Ne lance jamais :

```bash
docker system prune
docker volume prune
docker network prune
rm -rf /home/ubuntu/apps
rm -rf /home/ubuntu/*
docker rm -f $(docker ps -aq)
```

Ne modifie pas Search normal, Chat, Upload, Auth, Dashboard ou les fonctionnalités non-RFP, sauf si un test démontre une dépendance directe indispensable. Ne remplace pas Spring Boot, FastAPI, PostgreSQL/pgvector ou Ollama. N’ajoute pas LangGraph, AutoRFP, LlamaIndex ou un nouveau framework d’orchestration.

Travaille d’abord sur une branche dédiée :

```bash
git status --short
git branch --show-current
git switch -c fix/rfp-p0-definitive
```

Si une branche existe déjà, utilise une branche de travail équivalente et affiche son nom.

---

## 2. PREFLIGHT OBLIGATOIRE

Avant de modifier un fichier, affiche les sorties exactes :

```bash
pwd
find .. -maxdepth 2 -name package.json -o -name pom.xml -o -name pyproject.toml -o -name docker-compose.yml
sha256sum /home/ubuntu/upload/avaliance_copilot_backup_final.zip 2>/dev/null || true
git branch --show-current
git rev-parse HEAD
git status --short
git diff --stat
git diff --check
git log --oneline -10
```

Ensuite vérifie le projet réellement ouvert et repère ces fichiers :

```text
service-ia/app/main.py
service-ia/app/schemas.py
service-ia/app/generation/rfp_proposal.py
service-ia/app/generation/rfp_proposal_legacy.py
service-ia/app/generation/rfp_quality.py
service-ia/app/retrieval/vector_search.py
backend/src/main/java/com/avaliance/copilot/rfp/
backend/src/main/java/com/avaliance/copilot/search/service/IaClientService.java
backend/src/main/resources/db/migration/
frontend/src/pages/RfpPage.tsx
frontend/src/api/client.ts
frontend/src/types.ts
frontend/src/components/RfpProposalDocument.tsx
frontend/src/components/rfpProposalText.ts
frontend/nginx.conf
```

Ne modifie rien si le projet racine n’est pas celui qui contient ces composants ou si le backup de référence ne correspond pas. Dans ce cas, arrête-toi et signale la divergence.

---

## 3. PROBLÈMES À CORRIGER — AUCUN NE DOIT ÊTRE IGNORÉ

Le backup contient les défauts suivants, qui doivent être vérifiés puis corrigés :

1. FastAPI `/rfp` intercepte `mode == "full"` et renvoie un simple `202 {job_id,status}` sans job durable, sans statut, sans résultat, sans annulation et sans contrôle de propriétaire.
2. `rfp_proposal_legacy.py` contient une autre pipeline 19 sections qui n’est pas le même runtime que la pipeline actuelle. Il ne doit plus exister deux contrats RFP concurrents.
3. La nouvelle pipeline peut retourner une validation d’évidence positive alors que les citations/provenances ne sont pas réellement validées.
4. La matrice de conformité n’est pas construite à partir d’un vrai mapping requirement → section → evidence.
5. Le retrieval RFP utilise un plafond global qui peut priver les requirements suivants d’évidence.
6. Le contrat global brief/standard n’est pas strictement vérifié après génération et réparation.
7. La qualité est insuffisamment document-level : claims, bullets, body, anchors et evidence ne sont pas tous validés ensemble.
8. Le frontend affiche une logique 19 sections même pour brief et standard.
9. Le renderer affiche un objet `RfpBullet` directement au lieu de `bullet.text`.
10. L’export texte interpole un objet bullet au lieu d’utiliser `b.text`.
11. Le frontend peut afficher une erreur générique « serveur injoignable » pour des causes différentes : timeout, refus réseau, 422, 502, 503, contrat invalide ou annulation.
12. Les timeouts de plusieurs minutes permettent à une requête standard de rester bloquée très longtemps au lieu de respecter la deadline P0.
13. Les tests historiques imposent 19 sections pour tous les modes et mockent des bullets sous forme de strings, ce qui masque les vrais bugs.
14. Le texte de l’interface parle de « missions comparables », alors que le RFP de production doit être PDF-only.
15. Le runtime RFP doit interdire `MISSION`, `LEGACY_SYNTHETIC`, seeds, corpus synthétique et recherche web automatique.
16. Vérifie aussi les imports TypeScript, le build frontend, les erreurs de sérialisation Jackson/Pydantic et les chemins Docker/Nginx. Corrige tout défaut démontré par les tests.

---

## 4. CONTRAT PRODUIT FINAL

Implémente exactement ces modes :

| Mode | Exécution | Sections | Budget global |
|---|---|---:|---:|
| `brief` | synchrone | exactement 4 | `<=600` mots |
| `standard` | synchrone, défaut | exactement 6 | `650–750` mots |
| `full` | job asynchrone uniquement | exactement 19 | budget full documenté et validé |

Le mode standard doit respecter exactement cette orchestration :

```text
CALL A: analyse + requirements atomiques
→ retrieval PDF par requirement en parallèle
→ plan déterministe
→ CALL B: sections 1–3
→ CALL C: sections 4–6
→ validation/sanitation déterministe
→ réparation ciblée au maximum une fois si nécessaire
→ réponse conforme ou échec explicite
```

Objectifs de performance :

```text
P50 standard <= 60 s
P95 standard <= 90 s
hard deadline standard = 90 s
```

Ne résous jamais la lenteur en passant les timeouts à 600 secondes. Si la deadline est dépassée, retourne une erreur explicite avec code, étape et `request_id`.

---

## 5. PIPELINE PDF-ONLY ET PROVENANCE

Le RFP ne doit utiliser comme preuves que les PDF uploadés depuis la plateforme et indexés dans PostgreSQL/pgvector.

Les faits du brief peuvent être utilisés uniquement comme :

```text
client_fact
assumption_to_confirm
open_question
requirement
```

Ils ne doivent jamais être transformés en « références internes vérifiées ».

Pour chaque requirement atomique, construis un packet :

```json
{
  "requirement_id": "req-001",
  "status": "SUPPORTED | NO_RELEVANT_EVIDENCE",
  "evidence": [
    {
      "source_document_id": 1,
      "page": 4,
      "chunk_id": 82,
      "quote": "..."
    }
  ]
}
```

Règles :

- au maximum 2–3 chunks finaux par requirement ;
- déduplication par document/page/chunk ;
- aucun document hors PDF ;
- aucun scope `MISSION` ou `LEGACY_SYNTHETIC` ;
- aucune recherche web automatique ;
- aucune citation inventée ;
- tout claim factuel ou bullet factuel doit référencer un evidence ID autorisé ;
- un requirement sans preuve doit rester explicitement non supporté ;
- le source register doit contenir uniquement les sources effectivement citées.

Corrige le cap global du retrieval pour qu’il ne prive pas silencieusement les requirements suivants. Utilise une limite globale raisonnable calculée à partir du nombre de requirements, avec déduplication et budget de contexte, mais garde le plafond de 2–3 chunks par requirement.

---

## 6. QUALITÉ ET SANITATION DÉTERMINISTES

Implémente une validation au niveau document entier et au niveau section. Après génération, après sanitation et après réparation, tous les gates doivent être recalculés.

Gates obligatoires :

```text
info_density >= 6 unités ancrées / 100 mots
repetition_8gram <= 0.05
boilerplate_count == 0
max_sentence_words <= 25
unanchored_bullets == 0
unsupported_claims == 0
section_count == expected_section_count
word_count == mode_budget
```

La sanitation ne doit pas couper arbitrairement une phrase en supprimant son sens. Si elle ne peut pas rendre le texte conforme, le résultat doit être `degraded` ou échouer explicitement. Il est interdit de forcer `passed=true`.

`evidence_validation_passed` doit être calculé depuis la validation effective. Il ne doit jamais avoir une valeur positive par défaut.

La compliance matrix doit être générée ainsi :

```text
requirement_id
covered
section_keys
supporting_evidence_ids
coverage_reason
```

Une ligne ne peut être `covered=true` que si une section contient réellement une réponse reliée au requirement et si la preuve exigée existe lorsque le claim est factuel.

---

## 7. FULL — JOB DURABLE OBLIGATOIRE

Ne garde pas le faux retour `202 pending` sans persistance. Ajoute une migration Flyway et une table de jobs, adaptée aux conventions du projet, contenant au minimum :

```text
id
owner_user_id
request_payload_json
mode
status
progress_step
result_json ou référence de résultat
error_code
error_message_safe
created_at
started_at
finished_at
cancel_requested_at
cancelled_at
lease_owner
lease_expires_at
claim_token_hash
attempt_count
expires_at
```

Le contrat public doit fournir l’équivalent de :

```text
POST /api/rfp/jobs
GET  /api/rfp/jobs/{jobId}
GET  /api/rfp/jobs/{jobId}/result
POST /api/rfp/jobs/{jobId}/cancel
```

Comportement obligatoire :

- le POST full répond immédiatement `202` avec `jobId`, `status=queued` et `requestId` ;
- le worker réclame atomiquement le job ;
- un lease/claim token empêche deux workers de générer le même job ;
- le job survit au redémarrage du service ;
- les jobs dont le lease expire peuvent être repris ;
- seul le propriétaire ou un ADMIN peut consulter, récupérer ou annuler ;
- l’annulation est coopérative entre les étapes et pendant les appels Ollama lorsque possible ;
- un job annulé ne peut pas terminer en `completed` ;
- retries bornés et backoff explicite ;
- concurrence Ollama limitée ;
- retention configurable pour les jobs terminés/échoués/annulés ;
- aucune suppression de PDF ou de chunks lors du nettoyage.

Si le projet ne possède pas déjà de mécanisme worker fiable, implémente le plus petit mécanisme durable compatible avec Spring/PostgreSQL/FastAPI. N’ajoute pas de système externe inutile.

---

## 8. FRONTEND — CORRECTIONS OBLIGATOIRES

Corrige le contrat TypeScript et l’interface :

1. `RfpPage.tsx` doit importer correctement tous les hooks utilisés et passer `pnpm run build`.
2. Le mode par défaut doit être `standard`.
3. Brief/standard attendent une `RfpResponse` complète.
4. Full ne doit jamais tenter de rendre `{job_id,status}` comme une proposition ; il doit afficher job, progrès, polling, succès, erreur et annulation.
5. Le compteur doit afficher dynamiquement `4/4`, `6/6` ou `19/19`.
6. `RfpProposalDocument.tsx` doit rendre `bullet.text`, jamais l’objet complet.
7. `rfpProposalText.ts` doit exporter `b.text` avec anchor/citation lisible.
8. Ne rends pas `legacyMarkdown` dans le flux P0 normal.
9. Lors du démontage, annule le polling et l’AbortController.
10. Différencie timeout, network error, HTTP 422, HTTP 502, HTTP 503, contrat invalide et cancellation.
11. Affiche le `request_id` à l’utilisateur dans un détail copiable, sans afficher de secrets.
12. Remplace le texte « missions comparables » par une formulation PDF-only.
13. Supprime du formulaire RFP toute option qui active implicitement mission corpus ou web research.

---

## 9. TESTS À ÉCRIRE ET À FAIRE PASSER

### FastAPI/Python

Ajoute des tests pour :

- brief : exactement 4 sections, ≤600 mots ;
- standard : exactement 6 sections, 650–750 mots ;
- full : création d’un job durable en 202 ;
- status/result/cancel ;
- isolation owner/admin ;
- claim token et lease ;
- reprise d’un job après expiration ;
- cancellation avant, pendant et après une étape ;
- retention sans suppression des PDF ;
- PDF-only strict ;
- rejet de `MISSION`, `LEGACY_SYNTHETIC`, web et seeds ;
- 2–3 chunks maximum par requirement ;
- claims et bullets traçables ;
- gates de qualité document-level ;
- deadline et timeout ;
- concurrence Ollama bornée ;
- aucun faux succès après fallback.

### Spring Boot

Ajoute des tests pour :

- POST brief/standard avec réponse complète ;
- POST full avec 202 et jobId ;
- GET status/result/cancel ;
- ownership et ADMIN ;
- 422 validation ;
- 502 IA ;
- 503 timeout/refus connexion ;
- request ID corrélé ;
- réponse JSON stable ;
- absence de stub en production ;
- migration Flyway appliquée.

### Frontend

Réécris les mocks et tests avec :

```typescript
{ text: '...', anchor: { type: 'requirement', id: 'req-001' } }
```

Teste :

- affichage correct 4/6/19 ;
- aucun `[object Object]` ;
- export texte correct ;
- erreurs différenciées ;
- full polling/success/failure/cancel ;
- cleanup du polling ;
- texte UI PDF-only ;
- réponse JSON invalide correctement signalée.

### Intégration réelle

Avec PostgreSQL/pgvector et des PDF de test non synthétiques :

- upload/indexation ;
- standard basé réellement sur chunks PDF ;
- sources et pages vérifiables ;
- absence de mission/web evidence ;
- métriques CALL A/retrieval/B/C/validation/total ;
- test de concurrence ;
- mesure P50/P95 sur un échantillon documenté.

---

## 10. COMMANDES DE VALIDATION

Exécute les commandes adaptées au repository :

```bash
# Backend
./mvnw test

# FastAPI
pytest -q

# Frontend
pnpm install --frozen-lockfile
pnpm run lint
pnpm run build
pnpm exec playwright test --grep RFP
```

Si une commande n’existe pas, indique la commande équivalente réellement utilisée. Si une validation nécessite PostgreSQL, pgvector, Ollama ou GPU indisponible, marque-la explicitement `NOT RUN`, explique la cause et ne remplace pas cette preuve par un mock.

Après chaque échec :

1. lis l’erreur complète ;
2. corrige la cause ;
3. relance le test ciblé ;
4. relance la suite impactée ;
5. relance ensuite toute la suite RFP.

---

## 11. CRITÈRES DE SORTIE OBLIGATOIRES

Tu ne peux déclarer la mission réussie que si tu fournis :

| Critère | Preuve obligatoire |
|---|---|
| Un seul contrat RFP actif | routes et tests de routage |
| Brief conforme | test 4 sections / ≤600 mots |
| Standard conforme | test 6 sections / 650–750 mots |
| Standard rapide | timings observés et deadline |
| Full durable | migration + création/status/result/cancel |
| Ownership sécurisé | tests owner/admin |
| Cancellation réelle | test d’annulation non ambigu |
| PDF-only | test négatif mission/web/synthetic |
| Provenance correcte | mapping requirement/claim/source/page/chunk |
| Qualité réelle | rapport de tous les gates après réparation |
| Frontend correct | build + tests sans `[object Object]` |
| Erreurs diagnostiquables | tests timeout/502/503/422/network |
| Hors-scope intact | `git diff` limité au scope RFP |

Le rapport final doit afficher :

```text
files changed
migration added
API contract
exact test commands
exact pass/fail output summary
integration tests run/not run
latency sample size, P50 and P95
remaining risks
known unvalidated items
```

Ne dis pas « 100% définitif » si un critère est `NOT RUN`, si une preuve est uniquement mockée, si Ollama réel n’a pas été testé ou si un comportement est encore hypothétique. Dans ce cas, indique précisément ce qui manque au lieu de masquer l’incertitude.

**Commence maintenant par le preflight. Ensuite implémente les corrections ; ne réponds pas uniquement avec des recommandations.**
