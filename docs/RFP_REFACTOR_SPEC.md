# Prompt à donner à Antigravity — Refonte complète du moteur de propositions/RFP Avaliance

Tu es un **staff engineer / architecte IA senior spécialisé en RAG, génération de propositions commerciales et systèmes enterprise**. Tu travailles directement dans le dépôt `avaliance-copilot`. Ta mission est de **diagnostiquer, corriger, tester et livrer** la partie **Propositions / RFP** de bout en bout, sans casser l’authentification, la recherche documentaire, l’ingestion, les missions, l’administration ni le déploiement Docker/GPU.

## 0. Mode de travail obligatoire

1. Commence par lire le dépôt réel et vérifier chaque constat ci-dessous. Ne fais confiance ni aux anciens ZIP imbriqués, ni aux documents obsolètes, ni aux commentaires s’ils contredisent le code exécuté.
2. Crée une branche dédiée et un point de restauration avant toute modification. Ne modifie jamais `.env`, ne révèle aucun secret et ne versionne aucune clé.
3. Établis d’abord un plan court avec : causes racines, fichiers touchés, contrat API cible, stratégie de migration et tests. Puis implémente réellement le plan.
4. Ne te limite pas à changer un prompt. Corrige toute la chaîne : **brief → compréhension → recherche interne → recherche web optionnelle → sélection des preuves → plan RFP → rédaction → validation → réparation → rendu/export**.
5. Préserve les routes existantes, notamment `/api/rfp/generate`, ou fournis une migration rétrocompatible. Ne supprime aucun comportement fonctionnel sans test de non-régression.
6. N’arrête pas après une analyse. Termine avec du code exécutable, des tests, un rapport des modifications et les commandes exactes de validation/déploiement.
7. Si une hypothèse technique est incertaine, inspecte le code ou exécute un test. Ne simule pas un succès.

## 1. Architecture actuelle à comprendre

Le projet contient :

- `frontend/` : React + TypeScript + Vite.
- `backend/` : Spring Boot, route publique applicative `/api/rfp/generate`.
- `service-ia/` : FastAPI, Ollama local, BGE-M3, pgvector et génération IA.
- PostgreSQL/pgvector et orchestration Docker Compose GPU.
- Le chemin principal actuel est :
  `frontend/src/pages/RfpPage.tsx`
  → `frontend/src/api/client.ts::generateRfp`
  → `backend/.../rfp/RfpController.java`
  → `backend/.../rfp/RfpService.java`
  → `IaClientService.rfp(...)`
  → `service-ia/app/main.py::/rfp`
  → `service-ia/app/generation/service.py::generate_rfp_structure`.

Fichiers critiques à auditer avant de coder :

- `service-ia/app/generation/service.py`
- `service-ia/app/generation/rfp_proposal.py`
- `service-ia/app/generation/prompts.py`
- `service-ia/app/generation/ollama.py`
- `service-ia/app/retrieval/vector_search.py`
- `service-ia/app/similar_missions/`
- `service-ia/app/schemas.py`
- `service-ia/app/settings.py`
- `service-ia/tests/test_rfp*.py`
- `backend/src/main/java/com/avaliance/copilot/rfp/`
- `backend/src/main/java/com/avaliance/copilot/search/service/IaClientService.java`
- `frontend/src/pages/RfpPage.tsx`
- `frontend/src/components/RfpProposalDocument.tsx`
- `frontend/src/components/rfpProposalText.ts`
- `frontend/src/api/client.ts`
- `frontend/src/types.ts`
- `TEST_RFP.md`, `ARCHITECTURE_OVERVIEW.md`, `.env.example`, `docker-compose.yml`.

## 2. Règle de données non négociable

La **seule base interne réelle et autorisée pour produire les propositions** est constituée des **PDF téléversés depuis la plateforme, ingérés et indexés dans PostgreSQL/pgvector** (`source_documents`, `doc_chunk` et tables associées selon le schéma réel).

Les fichiers `data/corpus/mission-*.json` et les missions JSON synthétiques étaient uniquement un jeu de test de la phase initiale. Ils ne doivent jamais être interrogés, classés, cités, affichés ou utilisés pour enrichir une proposition en production. Ils peuvent rester dans des tests isolés/fixtures, mais doivent être exclus explicitement du runtime RFP par configuration et par tests.

Conséquences obligatoires :

- le RAG RFP recherche uniquement dans les chunks provenant des PDF uploadés via la plateforme et persistés dans PostgreSQL ;
- chaque preuve interne doit pointer vers le vrai `document_id`, le vrai nom du PDF, la page physique, le `chunk_id` et l’extrait exact stocké ;
- une proposition peut utiliser plusieurs PDF réels, avec diversification par document et déduplication des chunks ;
- si aucun PDF pertinent n’est trouvé, ne jamais basculer silencieusement vers les JSON de démonstration ; produire seulement des recommandations/hypothèses fondées sur le brief, avec un avertissement clair ;
- les sources Internet, si activées, sont seulement un enrichissement public complémentaire et ne remplacent jamais les PDF internes pour prouver l’expérience ou les références d’Avaliance ;
- ajouter un test qui échoue si un fichier `data/corpus/*.json`, une mission `synthetic=true` ou une table de démo alimente `/rfp` en mode production.

## 3. Causes racines déjà repérées — à confirmer puis corriger

### Cause critique A — le LLM n’écrit actuellement pas la proposition

Dans le code actuel, `generate_rfp_structure(...)` appelle `_proposal_sections(...)`, qui appelle `build_adaptive_proposal(...)`. Cette fonction compose des phrases et tableaux **codés en dur**. Elle ne fait aucun appel à `generate()`/Ollama et n’utilise pas réellement `RFP_PROMPT`.

Conséquence : le résultat est générique, répétitif, souvent orienté sécurité même lorsque le brief parle d’un autre sujet, et ne peut pas devenir une vraie réponse RFP professionnelle.

### Cause critique B — le prompt RFP est mort et contradictoire

`service-ia/app/generation/prompts.py` assigne `RFP_PROMPT` deux fois : une version à 6 sections, puis une version à 14 sections. Mais le flux RFP exécuté ne l’utilise pas. `TEST_RFP.md` parle de 19 sections, tandis que les tests actuels exigent un nombre adaptatif inférieur à 19. Le contrat produit n’a donc pas de source de vérité unique.

### Cause critique C — compréhension du brief trop fragile

`_extract_rfp_requirements(...)` repose sur une liste fermée de mots-clés et des regex. Cela duplique des phrases entières dans plusieurs champs, rate les synonymes, les formulations longues, les contraintes implicites, les critères d’évaluation, les dépendances, les exclusions et les questions commerciales.

### Cause critique D — preuves internes mal exploitées

Les mêmes trois extraits PDF sont copiés dans plusieurs sections sous la forme « Extrait de référence interne vérifiée… », sans transformation en claims précis ni mapping section/affirmation. La présence d’un PDF suffit pratiquement à activer la proposition alors que sa pertinence métier n’est pas validée au niveau de chaque affirmation.

### Cause critique E — données JSON de test encore présentes dans le flux conceptuel

Le dépôt contient environ 300 missions JSON synthétiques et répétitives créées uniquement pour tester le projet à son stade initial. Elles ne représentent pas les données métier. Le runtime RFP doit les ignorer totalement et travailler sur les PDF réellement uploadés, ingérés et indexés dans PostgreSQL/pgvector. Supprime toute dépendance de production entre `/rfp` et `find_similar_missions(...)` si cette fonction s’appuie sur ces JSON synthétiques. Garde les JSON uniquement comme fixtures de tests explicitement isolées.

### Cause critique F — aucune recherche Internet

Il n’existe actuellement aucun provider de recherche web métier pour la route RFP. Les seuls appels HTTP IA visibles ciblent Ollama. Il faut ajouter une recherche externe contrôlée, traçable, optionnelle et respectueuse de la confidentialité.

### Cause critique G — limites modèle/contexte

La configuration observée utilise `qwen3:8b`, un contexte de `8192` et `GENERATION_MAX_TOKENS=2048`. Ne change pas aveuglément de modèle : mesure la VRAM et la latence sur la `g4dn.xlarge`. Mais une RFP riche en JSON structuré, preuves et tableaux nécessitera probablement une stratégie multi-passes et un budget de sortie supérieur. Préférer une bonne orchestration au simple gonflement du prompt.

### Cause critique H — rendu/export insuffisant

Le frontend rend les sections mais fusionne visuellement faits du brief et recommandations dans le même bloc. Le téléchargement produit seulement un `.txt`. Les sources web n’ont aucun type ni composant. Il manque une vraie expérience de révision, une traçabilité claim/source claire et un export professionnel.

## 4. Décision produit : contrat RFP cible

Établis une seule source de vérité et mets à jour code, tests et documentation ensemble. Pour cette refonte, implémente une **proposition enterprise structurée en 19 sections**, chaque section pouvant être marquée `not_applicable` avec justification plutôt que remplie artificiellement :

1. Synthèse exécutive
2. Compréhension du contexte
3. Enjeux et problème à résoudre
4. Objectifs et résultats attendus
5. Périmètre inclus
6. Périmètre exclu
7. Solution fonctionnelle proposée
8. Architecture technique cible
9. Intégrations et interfaces
10. Sécurité, conformité et gouvernance des données
11. Démarche, phases et livrables
12. Planning et jalons
13. Équipe, rôles et gouvernance
14. Stratégie de tests et recette
15. Migration, déploiement et réversibilité
16. Conduite du changement, formation et transfert
17. Exploitation, support et maintenance
18. Risques, dépendances, hypothèses et points à clarifier
19. Références, différenciation Avaliance et prochaines étapes

Une section ne doit contenir que des éléments pertinents. L’API doit conserver un tableau `sections`, mais enrichir chaque section avec un statut et des claims typés. Le frontend ne doit plus dépendre d’un Markdown libre pour le contrat principal.

## 5. Modèle de provenance obligatoire

Chaque affirmation visible doit porter un type explicite :

- `brief_fact` : vient directement du brief client.
- `internal_evidence` : vient d’un PDF interne avec document, page physique, chunk et extrait exact.
- `web_evidence` : vient d’une source web avec URL canonique, titre, éditeur/domaine, date de publication si disponible, date d’accès et extrait.
- `recommendation` : recommandation Avaliance, jamais présentée comme un fait.
- `assumption` : hypothèse à confirmer.
- `question` : question de cadrage.

Crée un registre de sources stable et des IDs de claims. Une citation n’est valide que si :

1. l’ID existe ;
2. le claim est sémantiquement supporté par l’extrait ;
3. la source est autorisée pour ce type de claim ;
4. une mission synthétique n’est jamais transformée en preuve ;
5. une source web ne prouve jamais un fait spécifique au client ;
6. les chiffres, dates, normes, capacités et engagements ont une provenance explicite.

## 6. Pipeline IA à implémenter

### Étape 1 — Normalisation et analyse du brief

Créer un extracteur LLM en sortie JSON validée par Pydantic, avec fallback déterministe. Extraire au minimum :

- organisation/secteur ;
- contexte et déclencheur ;
- problème métier ;
- objectifs ;
- utilisateurs/personas ;
- fonctionnalités ;
- périmètre ;
- livrables ;
- technologies imposées ou existantes ;
- intégrations ;
- données/volumétrie ;
- sécurité/conformité ;
- planning et contraintes ;
- budget si explicitement fourni ;
- critères d’évaluation/acceptation ;
- dépendances ;
- exclusions ;
- hypothèses ;
- ambiguïtés et questions.

Ne copie pas une même phrase dans toutes les catégories. Conserver des offsets ou extraits exacts du brief pour prouver les `brief_fact`.

### Étape 2 — Plan de recherche

Produire plusieurs requêtes distinctes :

- recherche interne de missions/projets comparables ;
- recherche interne de preuves documentaires ;
- recherche web réglementaire/technologique/marché lorsque pertinente ;
- requêtes de vérification pour les affirmations sensibles.

Ne jamais envoyer le brief confidentiel brut à un provider externe. Construire des requêtes minimales, retirer noms, emails, identifiants, données personnelles et informations confidentielles. Ajouter un consentement/flag explicite.

### Étape 3 — Recherche interne exclusivement dans les PDF PostgreSQL

Réutiliser le RAG existant en imposant `corpus_scope="PDF"` et en vérifiant au niveau SQL/métadonnées que chaque chunk provient d’un PDF réellement uploadé depuis la plateforme :

- interroger PostgreSQL/pgvector, jamais `data/corpus/*.json` ni les missions synthétiques ;
- conserver `document_id`, `document_name`, page physique, `chunk_id`, score et extrait exact ;
- reranker par besoin, secteur, contraintes, livrables et proximité réelle ;
- appliquer un seuil de pertinence réel et calibré ;
- dédupliquer les chunks et diversifier les résultats par document ;
- exclure les documents archivés/supprimés/non prêts selon le schéma réel ;
- ne pas conditionner la création d’une proposition à la présence d’un PDF : sans preuve interne pertinente, produire une proposition fondée sur le brief et des recommandations clairement typées, avec diagnostic non bloquant ;
- ne jamais utiliser les JSON de démonstration comme fallback.

### Étape 4 — Recherche Internet contrôlée

Ajouter une abstraction `WebResearchProvider` et un provider désactivé par défaut. Implémenter au minimum un provider réel configurable, par exemple Tavily, Brave Search ou Serper, uniquement si sa clé est présente. Variables proposées :

- `RFP_WEB_RESEARCH_ENABLED=false`
- `RFP_WEB_PROVIDER=tavily`
- `RFP_WEB_API_KEY=...` ou variable spécifique au provider
- `RFP_WEB_MAX_RESULTS=8`
- `RFP_WEB_TIMEOUT_SECONDS=15`
- `RFP_WEB_ALLOWED_DOMAINS=`
- `RFP_WEB_BLOCKED_DOMAINS=`

Exigences : timeout, retries bornés, cache, allow/block list, validation URL, protection SSRF, taille maximale, sanitation HTML, journalisation sans secret, et fonctionnement correct si le web est désactivé/indisponible.

Prioriser les sources officielles et primaires : autorités, textes réglementaires, documentation éditeur, standards, publications techniques reconnues. Déclasser blogs SEO, agrégateurs et contenus sans date/auteur. Ne jamais inventer une URL.

### Étape 5 — Registre de preuves

Fusionner sans confondre :

- faits du brief ;
- PDFs internes ;
- missions réelles si disponibles ;
- missions synthétiques de démonstration ;
- sources web.

Attribuer score de pertinence, fraîcheur, autorité, couverture et risque. Dédupliquer. Conserver l’extrait exact qui justifie chaque claim.

### Étape 6 — Planification de la proposition

Faire un premier appel LLM structuré pour produire le plan des 19 sections, les claims prévus, les sources autorisées, les tableaux nécessaires et les questions non résolues. Le planner n’écrit pas encore la prose finale.

### Étape 7 — Rédaction contrôlée

Faire un ou plusieurs appels de rédaction par groupe de sections afin de respecter le contexte du modèle. Utiliser `output_schema` Ollama/Pydantic. La sortie doit être du JSON strict, pas du Markdown à parser.

Style attendu : français professionnel, précis, convaincant, spécifique au brief, lisible par un comité de direction et exploitable par une équipe projet. Une idée par phrase. Pas de jargon creux, pas de superlatifs gratuits, pas de fausse promesse, pas de données inventées.

Chaque section doit contenir selon le besoin :

- résumé exécutif ;
- paragraphes structurés ;
- claims typés ;
- listes actionnables ;
- tableaux structurés ;
- décisions attendues ;
- critères de sortie/acceptation ;
- hypothèses/questions ;
- références associées.

### Étape 8 — Contrôle qualité et réparation

Ajouter un validateur déterministe puis, si utile, un critique LLM. Vérifier :

- 19 sections présentes dans le bon ordre ;
- sections non pertinentes marquées, non remplies avec du texte générique ;
- couverture des exigences du brief ;
- aucune contradiction ;
- aucune citation inexistante ;
- aucune mission synthétique présentée comme réelle ;
- tous les nombres/dates/normes/technologies sensibles sourcés ;
- pas de fait client provenant du web ;
- tableaux rectangulaires et non vides ;
- absence de répétition inter-sections ;
- séparation faits/recommandations/hypothèses ;
- longueur et lisibilité ;
- aucune balise `<think>` ni texte hors JSON.

Si la validation échoue, lancer une seule réparation ciblée avec la liste exacte des violations. Si elle échoue encore, retourner un diagnostic contrôlé, jamais une sortie trompeuse.

## 6. Schéma API recommandé

Fais évoluer les schémas Pydantic/Java/TypeScript de façon rétrocompatible. Exemple conceptuel :

```json
{
  "requirements": {},
  "proposal": {
    "title": "Proposition de réponse — …",
    "executive_summary": "…",
    "sections": [
      {
        "key": "executive_summary",
        "order": 1,
        "title": "Synthèse exécutive",
        "status": "complete",
        "narrative": ["…"],
        "claims": [
          {
            "id": "claim-001",
            "text": "…",
            "kind": "brief_fact",
            "source_ids": ["brief-01"],
            "confidence": 1.0
          }
        ],
        "bullets": [],
        "tables": [],
        "questions": []
      }
    ]
  },
  "sources": [
    {
      "id": "web-01",
      "type": "web",
      "title": "…",
      "publisher": "…",
      "url": "https://…",
      "published_at": null,
      "accessed_at": "…",
      "excerpt": "…",
      "authority_score": 0.9
    }
  ],
  "similar_missions": [],
  "quality": {
    "passed": true,
    "score": 0.91,
    "coverage": 0.95,
    "citation_integrity": 1.0,
    "warnings": []
  },
  "diagnostic": null
}
```

Tu peux ajuster les noms, mais garde des objets structurés, validables et rendables sans parser du Markdown.

## 7. Frontend à livrer

Améliorer `/propositions` sans casser son design :

1. Ajouter option explicite « Enrichir avec des sources publiques » avec information confidentialité.
2. Afficher une progression réelle par étapes : analyse, recherche interne, recherche web, rédaction, contrôle qualité.
3. Séparer visuellement : fait du brief, preuve interne, source publique, recommandation, hypothèse, question.
4. Rendre les citations cliquables ; pour PDF, conserver page physique et chunk ; pour web, ouvrir l’URL canonique en nouvel onglet avec protections `noopener noreferrer`.
5. Afficher score qualité, couverture et avertissements utiles, sans faux pourcentage marketing.
6. Permettre copier et exporter proprement. P0 : Markdown/texte lisible. P1 : DOCX ou PDF professionnel généré côté serveur avec titres, tableaux, en-tête/pied de page et bibliographie.
7. Préserver les états loading/error/retry, accessibilité clavier, responsive et absence de crash sur ancienne réponse.
8. Ne fusionne plus silencieusement `factsFromBrief` et `recommendations` dans le même rendu.

## 9. Séparation stricte des données de test

- Exclure complètement `data/corpus/mission-*.json` et toute mission `synthetic=true` du runtime `/rfp`.
- Les conserver seulement comme fixtures de tests locaux si elles restent utiles.
- La liste « références comparables » doit être construite à partir des PDF uploadés dans PostgreSQL, regroupés par document/projet lorsque les métadonnées le permettent.
- Si les PDF ne possèdent pas assez de métadonnées pour identifier une mission, afficher « Documents internes pertinents » plutôt que prétendre qu’il s’agit de missions réalisées.
- Ne plus écrire « missions réellement réalisées » sans preuve provenant des PDF et métadonnées internes.
- Ajouter une garde de configuration et des tests d’intégration garantissant qu’aucune donnée JSON synthétique ne fuit dans une réponse de production.

## 10. Gestion du modèle et performance GPU

- Mesurer `nvidia-smi`, latence, VRAM, tokens/s et taux de JSON valide avec le modèle actuel.
- Commencer avec `qwen3:8b` et une orchestration multi-passes.
- Tester un contexte supérieur et `GENERATION_MAX_TOKENS` supérieur uniquement après mesure. Ne rends pas la machine instable.
- Si un modèle plus grand est proposé, fournir benchmark comparatif avant/après et garder un fallback configurable.
- Ajouter timeouts distincts par étape, budget global, annulation et logs corrélés par `request_id`.
- Ne loguer ni brief complet confidentiel, ni tokens, ni clés API.

## 11. Tests obligatoires

Mettre à jour les tests contradictoires au lieu de simplement les supprimer.

### Unitaires service IA

- extraction structurée de briefs variés ;
- fallback si JSON LLM invalide ;
- plan 19 sections ;
- provenance de chaque claim ;
- rejet citation inconnue ;
- rejet chiffre non sourcé ;
- mission synthétique jamais utilisée comme preuve ;
- web désactivé, timeout web et résultat web valide ;
- SSRF/URL non autorisée ;
- déduplication des sources ;
- réparation après violation ;
- sortie correcte sans preuve PDF.

### Contrat backend

- mapping snake_case/camelCase ;
- timeout et erreurs contrôlées ;
- audit `GENERATE_RFP` succès/échec ;
- rétrocompatibilité du endpoint.

### Frontend

- réponse complète ;
- source PDF ;
- source web ;
- aucune source ;
- réponse malformée ;
- retry ;
- séparation visuelle des types de claims ;
- export ;
- aucune erreur console.

### Golden set RFP

Créer au moins 8 briefs réalistes : santé/HDS, banque/cloud, assurance/data, télécom/plateforme, logistique/cybersécurité, énergie/IoT, secteur public/accessibilité, et un brief hors périmètre. Pour chacun, vérifier automatiquement et manuellement : couverture, exactitude, spécificité, citations, absence d’hallucination, qualité exécutive et actionnabilité.

Rubrique minimale sur 100 :

- couverture du brief : 20 ;
- exactitude/provenance : 25 ;
- spécificité et absence de générique : 15 ;
- qualité de la solution/démarche : 15 ;
- risques/gouvernance/acceptation : 10 ;
- qualité rédactionnelle exécutive : 10 ;
- qualité des sources : 5.

Bloquer la livraison si exactitude/provenance < 23/25 ou si une hallucination critique apparaît.

## 12. Validation et commandes

Exécuter autant que disponibles dans l’environnement :

```bash
docker compose config
cd service-ia && python -m pytest -q
cd ../backend && ./mvnw test
cd ../frontend && npm test --if-present && npm run build
# puis Playwright/E2E avec les variables nécessaires
```

Démarrer la stack, vérifier `/ready`, puis effectuer au moins deux appels réels à `/api/rfp/generate` : un avec sources internes/web et un sans preuve. Capturer les temps de réponse et valider le JSON.

## 13. Ordre de livraison

### P0 — obligatoire

- branch/backup ;
- source de vérité du contrat ;
- extraction LLM structurée ;
- génération LLM réellement appelée ;
- pipeline planner/writer/validator/repair ;
- claims typés et citations fiables ;
- fonctionnement sans PDF ;
- frontend lisible et séparant les natures d’information ;
- tests unitaires/contrats/build verts ;
- documentation mise à jour.

### P1 — obligatoire si la clé/provider est disponible

- recherche web contrôlée ;
- consentement UI ;
- source registry web ;
- protections réseau/confidentialité ;
- tests provider mockés.

### P2 — après P0/P1 stables

- export DOCX/PDF premium ;
- streaming/progression détaillée ;
- écran de relecture/édition ;
- benchmark modèle alternatif.

## 14. Définition de “terminé”

Le travail n’est terminé que si :

1. le code exécuté appelle réellement le LLM pour comprendre et rédiger la proposition ;
2. une RFP spécifique au brief, non générique, est produite ;
3. les 19 sections ont un contrat stable et un statut ;
4. chaque affirmation est typée et traçable ;
5. les preuves internes proviennent exclusivement des PDF uploadés et indexés dans PostgreSQL/pgvector, et les sources web restent séparées ;
6. aucun JSON synthétique ni fichier `data/corpus/mission-*.json` n’alimente le runtime RFP ;
7. aucune preuve PDF n’est nécessaire pour produire une recommandation honnête ;
8. les validations détectent chiffres/citations/hallucinations ;
9. frontend, backend et service IA sont cohérents ;
10. les tests pertinents et le build passent ;
11. le déploiement Docker reste fonctionnel sur la machine GPU ;
12. un rapport final liste fichiers modifiés, décisions, tests exécutés, résultats, limites restantes et rollback.

## 15. Format de ton rapport final

À la fin, réponds avec :

1. **Causes racines confirmées** ;
2. **Architecture cible implémentée** ;
3. **Fichiers modifiés** ;
4. **Contrat API final** ;
5. **Tests exécutés et résultats réels** ;
6. **Exemple avant/après d’une proposition** ;
7. **Mesures performance GPU/latence** ;
8. **Variables d’environnement ajoutées sans valeurs secrètes** ;
9. **Commandes de déploiement** ;
10. **Risques/limites restantes et rollback**.

Commence maintenant par inspecter les fichiers critiques et confirmer les causes racines. Ensuite implémente P0 complètement avant de passer à P1/P2.
