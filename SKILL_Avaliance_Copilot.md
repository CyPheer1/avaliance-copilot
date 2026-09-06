# SKILL — « Avaliance Copilot » Builder Agent

> **But de ce fichier.** Ce document est une *skill* (spécification exécutable) destinée à un IDE de vibe-coding agentique (Cursor, Windsurf, Bolt, Claude Code, Cline, etc.). Il décrit **de zéro à 100 %** comment construire l'application **Avaliance Copilot** — une plateforme d'intelligence documentaire (RAG hybride) pour la rédaction de propositions commerciales chez une ESN. L'agent qui lit ce fichier doit **construire le projet en entier, dans l'ordre, jusqu'à une démo fonctionnelle**, en respectant strictement les contraintes ci-dessous.

> **Langue.** Code, identifiants, commentaires techniques en anglais. Textes produits pour l'utilisateur (UI, corpus synthétique, réponses générées) en français.

---

## 0. Comment l'agent doit utiliser cette skill

1. **Lis ce fichier en entier avant d'écrire la moindre ligne.**
2. Traite la **section 16 (Plan d'exécution par phases)** comme ta feuille de route officielle. Suis l'ordre P0 → P5. Ne saute pas de phase.
3. À la fin de **chaque phase**, vérifie la *Definition of Done* (DoD) de cette phase avant de continuer. Si la DoD n'est pas remplie, corrige avant d'avancer.
4. Fais des commits Git atomiques et fréquents, un par jalon (voir §17). Si le dépôt n'est pas un dépôt Git, ne prétends jamais avoir créé un commit.
5. Quand un choix technique n'est pas précisé ici, prends la **décision la plus simple et la plus standard**, documente-la dans le `README.md`, et continue — ne bloque pas.
6. **Ne demande pas de confirmation à chaque étape.** Construis. Explique tes choix dans les commits et le README.
7. Tout doit tourner **en local via Docker Compose** d'abord. Le déploiement AWS vient en dernier (P5), sur une VM EC2 GPU.
8. Ne dégrade jamais les contrats déjà déployés : le modèle de génération est exclusivement `LLM_MODEL=qwen3:8b`, avec `think:false`, `OLLAMA_NUM_CTX=8192` et `GENERATION_MAX_TOKENS=1500`. Aucun fallback Llama, silencieux ou codé en dur, n'est permis.
9. Le corpus applicatif de recherche est **PDF par défaut**. Les données d'évaluation sont strictement séparées du corpus et doivent être créées à partir des PDF réellement indexés dans PostgreSQL, jamais à partir d'un ancien JSON non vérifié.

---

## 1. Rôle & mission de l'agent

Tu es un **ingénieur logiciel full-stack senior + ingénieur ML**. Tu construis un système polyglotte de bout en bout :

- un **backend Java / Spring Boot 3** (sécurité, métier, orchestration),
- un **service IA Python / FastAPI** (retrieval, embeddings, génération LLM),
- un **frontend React 18 + TypeScript**,
- une **base PostgreSQL + pgvector + tsvector**,
- un **LLM auto-hébergé via Ollama**,
- une **composante ML réelle** : fine-tuning contrastif d'un modèle d'embeddings.

La cible finale : une **démo reproductible** (un seul `docker compose up`) qui permet d'administrer un corpus PDF/DOCX/TXT, de poser une question métier, d'obtenir une **réponse sourcée avec citations documentaires**, de lister les **missions similaires** et de **générer une structure de proposition (RFP)**.

---

## 2. Règles d'or (non négociables)

1. **Données maîtrisées.** Le corpus métier chargé dans le produit et utilisé pour la démonstration reste **100 % synthétique** (300 missions fictives générées par script). Le pipeline ML hors-produit peut utiliser des jeux publics documentés (`mMARCO-fr`, `MIRACL-fr`, BOAMP) uniquement pour l'entraînement ou le benchmark, avec licence, provenance et séparation stricte des jeux consignées. En production, seuls les administrateurs peuvent importer des documents internes explicitement autorisés. Ne jamais coder en dur de vraies données client, ne jamais versionner les originaux importés et ne jamais les envoyer à une API LLM externe.
2. **Confidentialité totale.** Le LLM est **auto-hébergé (Ollama)**. **Aucun appel à une API LLM externe** (pas d'OpenAI, Anthropic, etc.) dans le chemin d'exécution du produit. La seule utilisation d'un LLM local hors-produit est la génération de paires d'entraînement (§12).
3. **Ce n'est PAS un chatbot.** C'est une **plateforme d'aide à la production** : réponses sourcées + structure RFP. Toujours privilégier le livrable structuré et sourcé.
4. **Pas d'hallucination silencieuse.** Si aucune source pertinente n'est trouvée, le système **signale explicitement** l'insuffisance d'information au lieu d'inventer.
5. **Séparation stricte des responsabilités.** Spring Boot = sécurité + métier + orchestration. FastAPI = service IA **stateless**, appelé uniquement en interne par Spring Boot, **jamais exposé directement au frontend**.
6. **GPU optionnel selon l'environnement.** Le développement local doit rester fonctionnel sur CPU. Le déploiement de test utilise une VM AWS EC2 `g4dn.xlarge` avec NVIDIA T4 pour accélérer Ollama. Le fine-tuning des embeddings se fait sur **Google Colab (GPU T4 gratuit)**, hors de la VM.
7. **Reproductibilité.** Tout se lance via **Docker Compose**. Fournir `.env.example`, seeds, et un `README.md` de démarrage complet.
8. **Non-goals stricts** (voir §19) : **pas** de Neo4j / GraphRAG, **pas** d'agents autonomes multi-LLM, **pas** d'OCR ni d'ingestion documentaire lourde. Le MVP accepte uniquement les PDF textuels, DOCX et TXT.

---

## 3. Vue d'ensemble du produit

**Problème résolu.** Une ESN capitalise des milliers de missions, propositions et documents. La connaissance est fragmentée : chaque réponse à appel d'offres (RFP) repart de zéro et l'onboarding des consultants est lent. Avaliance Copilot rend ce patrimoine **interrogeable de façon fiable et sourcée**, avec une administration contrôlée des sources et sans exposer les documents à un fournisseur LLM externe.

**Objectifs fonctionnels.**
1. Restituer une **réponse sourcée** à partir du corpus interne (avec citations + score de confiance).
2. Identifier les **missions similaires** à un nouveau besoin.
3. Générer une **structure de proposition (RFP)** à partir des missions comparables.
4. **Mesurer sa propre qualité** via un banc d'évaluation quantitatif.
5. Permettre à un **ADMIN** d'importer, suivre, relancer, télécharger et supprimer les sources PDF textuelles, DOCX et TXT, tout en conservant l'original pour la traçabilité.

---

## 4. Contraintes & garde-fous

| Contrainte | Règle |
|---|---|
| Durée | ~8 semaines / 2 mois (périmètre de stage). Le MVP est prioritaire. |
| Matériel | Local : CPU compatible. Sur le déploiement GPU, `docker-compose.yml` attribue par défaut `gpus: all` à Ollama **et** au service IA : Qwen et le reranker CUDA utilisent la Tesla T4 lorsque disponible. |
| Fine-tuning | Google Colab (GPU T4 gratuit), 1–3 epochs ; le runtime charge par défaut le modèle local fine-tuné. |
| Cloud | AWS EC2 `g4dn.xlarge`, Ubuntu 24.04, 4 vCPU, 16 Go RAM, NVIDIA T4 et 150 Go EBS gp3. Instance démarrée/arrêtée à la demande. |
| Données | Corpus métier de démo 100 % synthétique ; datasets publics autorisés seulement dans le pipeline ML hors-produit avec licence/provenance ; documents internes autorisés uniquement via l'espace ADMIN, conservés localement et jamais envoyés à une API LLM externe. |
| Réseau LLM | Aucun appel LLM externe dans le produit. |
| Corpus | 200–300 missions synthétiques + documents administrés PDF textuels, DOCX et TXT (20 Mo maximum par fichier). |

---

## 5. Architecture cible (microservices)

```
[ React 18 + TypeScript ]  ──HTTP──▶  [ Spring Boot 3 ]  ──HTTP interne──▶  [ FastAPI (service IA, stateless) ]
      Frontend                        Backend principal                         Service IA
                                       - Auth JWT / rôles                         - Retrieval hybride (vecteur + BM25/tsvector + RRF)
                                       - Logique métier                          - Génération d'embeddings
                                                                             - Documents / stockage                    - Extraction PDF/DOCX/TXT + chunking
                                                                             - Orchestration / audit                   - Appel LLM (Ollama) + garde-fou anti-hallucination
                                            │                                          │
                                                            ┌─────────────┴─────────────┐                            ▼
                                                            ▼                           ▼                   [ Ollama (AWS EC2 GPU / CPU local) — qwen3:8b ]
                                        [ Volume document_storage ] [ PostgreSQL + pgvector + tsvector ]    LLM auto-hébergé
                                             fichiers originaux         métadonnées, chunks, index
```

**Règles d'architecture.**
- Le frontend ne parle **qu'à** Spring Boot.
- Spring Boot appelle FastAPI en HTTP interne (réseau Docker), avec un secret partagé / header d'authentification service-à-service.
- FastAPI est **stateless** : pas de session, pas d'état utilisateur. Il lit/écrit PostgreSQL et appelle Ollama.
- Spring Boot est propriétaire du cycle de vie documentaire : autorisation ADMIN, stockage de l'original, SHA-256, statuts, téléchargement, relance et suppression.
- FastAPI extrait le texte puis remplace atomiquement les chunks et embeddings d'un document. Les PDF conservent leurs numéros de page réels ; DOCX/TXT restent sans page de citation artificielle.
- PostgreSQL est la source de vérité pour les métadonnées, chunks, embeddings et index texte ; le volume Docker `document_storage` conserve les octets originaux.
- La suppression d'une source retire son original et ses chunks associés par cascade.

---

## 6. Stack technique détaillée (versions cibles)

| Composant | Techno | Rôle |
|---|---|---|
| Backend principal | **Spring Boot 3.3.x**, Java 17, Maven, Spring Security, Spring Data JPA | Auth JWT, rôles, métier, orchestration, audit |
| Service IA | **FastAPI** (Python 3.11), Uvicorn, Pydantic v2 | Retrieval hybride, embeddings, appel LLM, génération |
| Base | **PostgreSQL 16** + **pgvector** (image `pgvector/pgvector:pg16`) + `tsvector` | Embeddings, index texte, métadonnées |
| Frontend | **React 18 + TypeScript**, Vite, CSS responsive, TanStack Query, React Router, Lucide | UI de consultation, administration documentaire et génération RFP |
| LLM | **Ollama** — `qwen3:8b` | LLM auto-hébergé, accéléré par GPU sur AWS et compatible CPU en local |
| Embeddings | `BAAI/bge-m3` | Vectorisation multilingue FR/EN |
| Fine-tuning | `sentence-transformers` (open-source) | Apprentissage contrastif des embeddings |
| Orchestration | **Docker Compose** | Déploiement reproductible |
| Cloud | **AWS EC2** (VM Linux GPU) | Hébergement de la démo et des tests |

> Utilise `pip` / `requirements.txt` pour Python et Maven `pom.xml` pour Java. Fige les versions majeures. Pas de dépendance à une API LLM tierce.

---

## 7. Structure du dépôt (à créer exactement)

```
avaliance-copilot/
├── backend/                         # Spring Boot 3 (backend principal)
│   ├── src/main/java/com/avaliance/copilot/
│   │   ├── auth/                    # Spring Security, JWT, users, roles
│   │   ├── document/                # Stockage, cycle de vie et API ADMIN des sources
│   │   ├── mission/                 # Entités, repositories, services "missions"
│   │   ├── rfp/                     # Orchestration génération RFP
│   │   ├── search/                  # Proxy d'orchestration vers FastAPI (retrieval/generation)
│   │   ├── audit/                   # Journalisation des requêtes
│   │   ├── config/                  # Config, clients HTTP, CORS, sécurité
│   │   └── CopilotApplication.java
│   ├── src/main/resources/application.yml
│   ├── src/test/java/...            # Tests JUnit
│   ├── Dockerfile
│   └── pom.xml
│
├── service-ia/                      # FastAPI (service IA, stateless)
│   ├── app/
│   │   ├── ingestion/               # Extraction PDF/DOCX/TXT, chunking et indexation atomique
│   │   ├── retrieval/               # Vector + tsvector + RRF + BGE cross-encoder reranking
│   │   ├── similar_missions/        # Requête SQL "missions similaires"
│   │   ├── generation/              # Preuves, citations/spans validés, Ollama et SSE
│   │   ├── embeddings/              # Chargement du modèle fine-tuné ou du modèle de base
│   │   ├── schemas.py               # Modèles Pydantic (I/O)
│   │   ├── db.py                    # Accès PostgreSQL
│   │   ├── settings.py              # Config via env
│   │   └── main.py                  # App FastAPI + routes
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                        # React 18 + TypeScript (Vite)
│   ├── src/
│   │   ├── pages/                   # Search, Documents (ADMIN), Users, Dashboard, Login
│   │   ├── components/
│   │   ├── api/                     # Client HTTP vers Spring Boot
│   │   └── main.tsx
│   ├── Dockerfile
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
│
├── ml/                              # Fine-tuning des embeddings
│   ├── notebooks/finetune_embeddings.ipynb   # Google Colab (GPU T4)
│   └── generate_synthetic_pairs.py           # Paires question↔document via LLM local
│
├── data/
│   ├── generate_synthetic_corpus.py          # 300 missions fictives
│   └── corpus/                               # Sortie générée (JSON)
│
├── docker-compose.yml               # postgres+pgvector, Ollama GPU, service-ia GPU, backend, frontend
│                                      # + volume nommé document_storage monté sur le backend
├── docker-compose.gpu.yml           # compatibilité/override NVIDIA historique ; le GPU est déjà actif par défaut
├── benchmarks/
│   ├── pdf-golden-v2.json           # golden evaluation-only fondé sur les PDF indexés
│   └── results/                     # résultats versionnés, jamais utilisés pour entraîner
├── scripts/
│   └── evaluate_pdf_golden.py       # évaluation publique authentifiée du golden PDF
├── .env.example
├── Makefile                         # raccourcis: up, down, seed, bench, finetune-eval
└── README.md
```

---

## 8. Modèle de données (schéma PostgreSQL)

Flyway, depuis `backend/src/main/resources/db/migration/`, est l'unique propriétaire du schéma. `V1__schema.sql` crée l'extension pgvector et le socle ; `V2__source_documents.sql` ajoute le registre documentaire et sa provenance. Ne jamais modifier une migration déjà appliquée : ajouter une nouvelle migration versionnée. La dimension de la colonne d'embedding doit correspondre exactement au modèle de service BGE-M3 : **1024**.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- Missions synthétiques (métadonnées de haut niveau)
CREATE TABLE mission (
    id            BIGSERIAL PRIMARY KEY,
    title         TEXT NOT NULL,
    sector        TEXT NOT NULL,            -- banque, assurance, telecom, transport...
    mission_type  TEXT NOT NULL,            -- modernisation, migration cloud, data, cybersécurité...
    technologies  TEXT[] NOT NULL,          -- ['Java','Spring','Azure','Kubernetes']
    year          INT NOT NULL,
    referent_tag  TEXT,                     -- "profil référent" anonymisé (métadonnée légère)
    summary       TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- Segments documentaires (chunks) indexés en vecteur + texte
CREATE TABLE doc_chunk (
    id            BIGSERIAL PRIMARY KEY,
    mission_id    BIGINT REFERENCES mission(id) ON DELETE CASCADE, -- nullable pour une source importée
    chunk_index   INT NOT NULL,
    content       TEXT NOT NULL,
    sector        TEXT,
    mission_type  TEXT,
    technologies  TEXT[],
    year          INT,
    embedding     vector(1024),             -- pgvector
    ts            tsvector GENERATED ALWAYS AS (to_tsvector('french', content)) STORED
);

-- Index
CREATE INDEX idx_doc_chunk_embedding ON doc_chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_doc_chunk_ts        ON doc_chunk USING gin (ts);
CREATE INDEX idx_doc_chunk_sector    ON doc_chunk (sector);
CREATE INDEX idx_doc_chunk_type      ON doc_chunk (mission_type);

-- Utilisateurs (auth)
CREATE TABLE app_user (
    id            BIGSERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'CONSULTANT'  -- ADMIN | CONSULTANT
);

-- Journal d'audit (traçabilité des requêtes)
CREATE TABLE audit_log (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT REFERENCES app_user(id),
    action        TEXT NOT NULL,            -- SEARCH | GENERATE_RFP | SIMILAR
    query_text    TEXT,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- Registre des fichiers originaux administrés (migration Flyway dédiée)
CREATE TABLE source_document (
    id                BIGSERIAL PRIMARY KEY,
    original_filename TEXT NOT NULL,
    storage_key       TEXT NOT NULL UNIQUE,
    media_type        TEXT NOT NULL,
    size_bytes        BIGINT NOT NULL CHECK (size_bytes > 0),
    sha256            CHAR(64) NOT NULL,
    status            VARCHAR(20) NOT NULL CHECK (status IN ('STORED', 'PROCESSING', 'INDEXED', 'FAILED')),
    uploaded_by       BIGINT NOT NULL REFERENCES app_user(id),
    page_count        INT,
    chunk_count       INT,
    error_message     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    indexed_at        TIMESTAMPTZ
);

ALTER TABLE doc_chunk
    ADD COLUMN source_document_id BIGINT REFERENCES source_document(id) ON DELETE CASCADE,
    ADD COLUMN source_page INT CHECK (source_page IS NULL OR source_page >= 1);

CREATE INDEX idx_source_document_status ON source_document (status);
CREATE INDEX idx_doc_chunk_source_document ON doc_chunk (source_document_id);
CREATE UNIQUE INDEX idx_doc_chunk_source_position
    ON doc_chunk (source_document_id, chunk_index)
    WHERE source_document_id IS NOT NULL;
```

> Choisis `hnsw` si pgvector le supporte dans l'image ; sinon `ivfflat`. Documente le choix.

**Invariant de provenance :** un chunk est rattaché à une mission synthétique (`mission_id`) ou à un document importé (`source_document_id`). Les contrats de recherche acceptent donc un `missionId` nullable. Une citation documentaire contient `documentId`, `documentName` et, seulement pour un PDF lorsque disponible, `page`.

---

## 9. Génération du corpus synthétique (`data/generate_synthetic_corpus.py`)

- Génère **300 missions fictives** couvrant plusieurs secteurs (banque, assurance, télécom, transport, énergie), plusieurs types (modernisation applicative, migration cloud, data/BI, cybersécurité, DevOps), et des stacks variées (Java/Spring, React, Azure, Kubernetes, PostgreSQL, etc.).
- Chaque mission a : titre, secteur, type, technologies, année, résumé (contexte + solution + résultats), 2–4 « documents » textuels (contexte projet, note d'architecture, retour d'expérience, extrait de proposition).
- Le ton s'inspire de cas d'usage publics d'ESN (ex. modernisation réglementaire type Solvabilité II) **sans jamais reprendre de contenu réel**.
- Sortie : fichiers JSON dans `data/corpus/`.
- Prévoir un flag pour générer via le LLM local (Ollama) **ou** via des gabarits déterministes (templates + variations), afin de fonctionner même hors-ligne.

**Definition of Done :** exécuter le script produit ≥ 300 missions et ≥ 800 chunks exploitables.

---

## 10. Spécifications des services

### 10.1 Backend Spring Boot (`backend/`)

**Responsabilités :** authentification JWT + rôles, logique métier missions, administration et stockage des documents originaux, orchestration des appels vers FastAPI, journalisation d'audit, exposition de l'API REST publique consommée par le frontend.

**Endpoints REST (publics, consommés par React) :**

| Méthode | Route | Rôle | Description |
|---|---|---|---|
| POST | `/api/auth/login` | public | Retourne un JWT |
| POST | `/api/auth/register` | ADMIN | Crée un utilisateur |
| GET | `/api/missions` | auth | Liste/filtre les missions (secteur, type, année) |
| GET | `/api/missions/{id}` | auth | Détail d'une mission |
| POST | `/api/search` | auth | Recherche hybride sourcée → proxy FastAPI `/retrieve` + `/generate` |
| POST | `/api/similar` | auth | Missions similaires à un besoin → proxy FastAPI `/similar` |
| POST | `/api/rfp/generate` | auth | Génère une structure de proposition → orchestration |
| POST | `/api/documents` | ADMIN | Stocke un PDF/DOCX/TXT puis déclenche son extraction et son indexation |
| GET | `/api/documents` | ADMIN | Registre paginé des sources et de leur état |
| GET | `/api/documents/{id}/content` | ADMIN | Télécharge l'original authentifié |
| POST | `/api/documents/{id}/index` | ADMIN | Relance l'indexation d'une source en échec |
| DELETE | `/api/documents/{id}` | ADMIN | Supprime l'original, la métadonnée et les chunks associés |

**Détails :**
- Spring Security avec filtre JWT (HS256, secret via env). Rôles `ADMIN`, `CONSULTANT`.
- Client HTTP interne (WebClient/RestClient) vers FastAPI, base URL via env `IA_SERVICE_URL`, header secret `X-Internal-Token`.
- Chaque requête métier écrit une ligne dans `audit_log`.
- CORS configuré pour l'origine du frontend.
- Validation des entrées (Bean Validation).
- Upload multipart limité à **20 Mo** par fichier (**21 Mo** par requête), extensions autorisées : `.pdf`, `.docx`, `.txt`.
- L'original est écrit sous `DOCUMENT_STORAGE_PATH`, identifié par une clé de stockage non prédictible et vérifié par SHA-256. Un échec d'extraction/indexation conserve la source avec le statut `FAILED` afin de permettre une relance.
- Tests JUnit sur l'auth et l'orchestration (mock FastAPI).

### 10.2 Service IA FastAPI (`service-ia/`)

**Responsabilités :** retrieval hybride, embeddings, appel LLM, génération sourcée, missions similaires. **Stateless**, appelé uniquement par Spring Boot (vérifie `X-Internal-Token`).

**Endpoints internes :**

| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | Liveness |
| POST | `/embed` | Encode un texte → vecteur (modèle base ou fine-tuné) |
| POST | `/ingest` | Chunking + embeddings + insertion `doc_chunk` |
| POST | `/documents/ingest` | Reçoit l'original et son identifiant, extrait PDF/DOCX/TXT puis remplace atomiquement ses chunks |
| POST | `/retrieve` | Recherche hybride (vecteur + tsvector) fusionnée par **RRF** + filtres métadonnées → top-k chunks |
| POST | `/similar` | Missions similaires (jointure tags + cosinus pondéré) |
| POST | `/generate` | Génère une réponse LLM sourcée à partir des chunks + garde-fou anti-hallucination |
| POST | `/rfp` | Construit une structure de proposition à partir des missions similaires |

**Détails d'implémentation :**
- Chargement du modèle d'embeddings au démarrage (variable `EMBEDDING_MODEL_PATH` : base HuggingFace **ou** modèle fine-tuné monté en volume).
- `/retrieve` est **PDF-default** : il exécute en parallèle recherche vectorielle et `tsvector`, les fusionne par RRF pondéré, puis applique le cross-encoder `BAAI/bge-reranker-v2-m3`. Il préserve l'évidence lexicale, les meilleurs candidats RRF/vectoriels, les projets explicitement nommés et diversifie les pages finales.
- `/retrieve/trace` est un endpoint interne authentifié d'évaluation ; il expose filtres, candidats, scores, sélection et durées sans modifier le contrat public.
- `/generate` et `/generate/stream` utilisent uniquement `LLM_MODEL`, avec `think:false`, température `0`, contexte/tokens configurés. La readiness vérifie la disponibilité du tag exact. La réponse comporte citations, preuves, offsets de spans, état de validation et diagnostic (`NO_RELEVANT_EVIDENCE`, `UNSUPPORTED_ANSWER`, `INVALID_CITATION_FORMAT`).
- Les extracteurs déterministes peuvent traiter certaines intentions avant le LLM. La validation garantit la présence textuelle des preuves ; elle ne remplace pas une validation d'entailment ni de couverture des sous-questions.
- `/documents/ingest` : PDF textuel avec pages 1-based, paragraphes/tableaux DOCX, TXT UTF-8 (BOM accepté) avec fallback CP1252. Retourne 415 pour un format non supporté, 422 pour un fichier illisible/vide/sans texte et 503 si les embeddings sont indisponibles.
- Aucun OCR : un PDF scanné sans couche texte est rejeté explicitement.
- Appel Ollama via son API HTTP (`OLLAMA_URL`), modèle via `LLM_MODEL`.
- Toutes les entrées/sorties typées avec Pydantic (`schemas.py`).

### 10.3 Frontend React (`frontend/`)

**Pages :**
- **Login** — auth JWT.
- **Search** — champ de question + filtres (secteur, type, année) → affiche la **réponse sourcée**, les **citations cliquables** et le **score de confiance**.
- **RFP Generator** — saisie d'un besoin/cahier des charges → affiche les **missions similaires** + une **structure de proposition** générée.
- **Results / Mission detail** — visualisation d'une mission et de ses chunks.
- **Documents (ADMIN)** — glisser/sélectionner un PDF/DOCX/TXT, suivre les statuts `STORED`, `PROCESSING`, `INDEXED`, `FAILED`, consulter pages/chunks/erreurs, relancer, télécharger l'original et supprimer avec confirmation.

**Détails :** Vite, TanStack Query pour les appels, stockage du JWT, garde de routes authentifiées et contrôle de rôle ADMIN, envoi multipart sans forcer `Content-Type: application/json`, téléchargement blob authentifié, validation cliente à 20 Mo, états de chargement (le LLM CPU peut prendre 30 s–2 min : afficher un spinner + message).

---

## 11. Chaîne de traitement (pipeline)

1. **Stockage contrôlé** — l'ADMIN envoie un PDF/DOCX/TXT à Spring Boot ; l'original est conservé dans `document_storage`, son SHA-256 et son état sont enregistrés dans `source_document`.
2. **Extraction** — FastAPI extrait la couche texte du PDF en conservant les pages, les paragraphes/tableaux DOCX ou le texte TXT. Les fichiers chiffrés, corrompus, vides ou sans texte sont rejetés ; aucun OCR n'est lancé.
3. **Ingestion** — découper le corpus synthétique ou le texte extrait en chunks ; une réindexation remplace atomiquement les anciens chunks du document.
4. **Vectorisation** — encoder chaque chunk brut avec BGE-M3 → colonne `embedding` (pgvector) ; la colonne `ts` (tsvector français) est générée pour la recherche mots-clés.
5. **Recherche hybride** — exécuter en parallèle la recherche vectorielle et la recherche texte (`ts_rank`, tsvector), puis fusionner les classements via **Reciprocal Rank Fusion (RRF)**. Les chunks documentaires restent recherchables même sans mission associée.
6. **Missions similaires** — requête SQL : jointure sur tags partagés (secteur/techno/type) + score cosinus pondéré → top missions proches.
7. **Génération** — le LLM produit une réponse à partir des chunks récupérés, **avec citations de mission ou de document** et score de confiance ; une correspondance lexicale positive peut franchir le seuil de pertinence sans gonfler artificiellement la confiance vectorielle.
8. **Garde-fou anti-hallucination** — si aucune source pertinente n'est trouvée par les canaux vectoriel ou lexical, signaler explicitement « information insuffisante » plutôt qu'inventer.
9. **Cycle de vie** — une source en échec peut être relancée ; son original peut être téléchargé ; sa suppression retire le fichier et les chunks par cascade.

> Implémente RRF côté FastAPI (ou en SQL). Formule RRF : `score(d) = Σ 1/(k + rank_i(d))`, avec `k≈60`.

---

## 12. Composante ML — fine-tuning des embeddings (`ml/`)

**Objectif :** dépasser une simple intégration d'outils avec une vraie phase d'apprentissage machine, **mesurable et défendable**.

### 12.1 Stratégie de données retenue

- **Entraînement général français :** échantillonner **60 000 à 100 000 triples** `(query, positive, negative)` depuis la configuration française de [mMARCO](https://github.com/unicamp-dl/mMARCO), sous licence Apache-2.0. Ne pas télécharger le dépôt complet (~93,8 Go) : utiliser le streaming Hugging Face ou les seuls fichiers français nécessaires.
- **Adaptation au domaine ESN/RFP :** produire **5 000 à 10 000 paires/triples** à partir du corpus synthétique Avaliance et, si utile, d'avis publics [BOAMP](https://www.data.gouv.fr/datasets/boamp). Les données BOAMP servent uniquement de matière documentaire publique ; les questions et labels de pertinence sont générés puis contrôlés par le pipeline local.
- **Mélange cible :** environ **80 % mMARCO-fr / 20 % Avaliance-BOAMP**. Conserver la provenance et la licence de chaque exemple dans le manifest du dataset final.
- **Benchmark externe indépendant :** réserver **MIRACL-fr dev** (343 requêtes, 3 429 jugements) exclusivement à l'évaluation générale. Ne jamais l'inclure dans l'entraînement ni dans la sélection des hard negatives.
- **FQuAD :** facultatif et exclu du chemin principal, car il s'agit d'un dataset de lecture extractive sans structure de ranking négatif adaptée à notre objectif.
- **Anti-fuite :** effectuer les splits par mission/document, jamais par chunk ou question. Les cas golden, notamment **Atlas Finance**, restent exclusivement dans le test interne et ne participent ni à l'entraînement ni au réglage des hyperparamètres.
- **Kaggle :** utiliser le GPU T4 pour l'entraînement, mais récupérer les datasets depuis leurs sources officielles GitHub/Hugging Face. Éviter les mirrors Kaggle dont la provenance, la licence ou les passages positifs/négatifs sont incomplets.

### 12.2 Pipeline d'entraînement

1. **Génération des paires (`generate_synthetic_pairs.py`)** — pour chaque document du corpus synthétique Avaliance et chaque document BOAMP sélectionné, le **LLM local (Ollama)** produit 2–3 questions auxquelles ce document répond (*synthetic query generation*). Construire des hard negatives issus du même secteur, type de mission ou stack technologique, mais ne répondant pas à la question. Sortie : paires/triples versionnés sans annotation client réelle.
   - **Limite à documenter (soutenance) :** questions générées par le même LLM que la génération de réponses → risque de biais de style. Le nommer explicitement.
2. **Entraînement (`notebooks/finetune_embeddings.ipynb`, Google Colab GPU T4)** —
   - Bibliothèque : `sentence-transformers`.
   - Modèle de production : `BAAI/bge-m3`.
    - Loss : `MultipleNegativesRankingLoss` ou sa variante cached si la mémoire GPU l'exige.
    - Entraînement FP16, 1–3 epochs, avec early stopping ou sélection sur le jeu de validation interne. Sauvegarder le modèle fine-tuné et ses hyperparamètres.
3. **Intégration** — le service FastAPI charge `BAAI/bge-m3` depuis le cache Hugging Face persistant.

**Definition of Done :** le dataset final possède un manifest de provenance/licences et des splits sans fuite ; le modèle fine-tuné est exporté avec ses hyperparamètres et chargeable dans FastAPI.

---

## 14. Infrastructure & déploiement

### 14.1 `docker-compose.yml` (5 services)

- `postgres` — image `pgvector/pgvector:pg16`, volume persistant ; le backend applique les migrations Flyway au démarrage.
- `ollama` — image `ollama/ollama`, volume pour les modèles, modèle requis par `LLM_MODEL` (actuellement `qwen3:8b`). Le compose principal définit `gpus: all`, `NVIDIA_VISIBLE_DEVICES=all` et les capacités `compute,utility`.
- `service-ia` — build `service-ia/`, dépend de `postgres` + `ollama` et reçoit également `gpus: all` pour PyTorch/CUDA et le reranker.
- `backend` — build `backend/`, dépend de `postgres` + `service-ia`.
- `frontend` — build `frontend/`, sert l'app (Vite/Nginx), parle à `backend`.
- Volume nommé `document_storage` — monté sur le backend à `/data/documents` pour conserver les originaux au-delà du cycle de vie des conteneurs.

> Démarrer `postgres` et `ollama` en premier pour valider l'infra avant toute logique métier.

### 14.2 Benchmark de latence (dès la semaine 1 — POINT DE VIGILANCE N°1)

Un LLM quantifié sur CPU peut prendre **30 s à 2 min** par génération. Chronométrer d'abord le fallback CPU local, puis la cible GPU AWS :
```bash
docker exec -it ollama ollama pull qwen3:8b
# Chronométrer une génération avec ~2000 tokens de contexte injectés
```
Le modèle de démonstration retenu est `qwen3:8b`. Après une génération, vérifier l'utilisation GPU avec `nvidia-smi`, les logs Ollama contenant `using device CUDA0`, `ollama ps` indiquant un processeur GPU et `torch.cuda.is_available() == True` dans `service-ia`.

### 14.3 Déploiement AWS EC2 GPU (P5)

- VM AWS EC2 `g4dn.xlarge` avec Ubuntu 24.04, NVIDIA T4 et 150 Go EBS gp3. Tout est conteneurisé, `docker compose up` sur la VM.
- Installer Docker et NVIDIA Container Toolkit. Le compose principal configure déjà `gpus: all` pour Ollama et `service-ia`; recréer ces services après tout changement GPU.
- Vérifier au démarrage que Qwen est chargé sur CUDA et que le reranker détecte la T4. Une disponibilité du périphérique seule ne suffit pas : valider pendant une inférence réelle.
- Ouvrir uniquement SSH depuis l'IP administrateur et le port frontend de test ; ne jamais exposer PostgreSQL, FastAPI ou Ollama.
- Développement local ; démo dans le cloud. **Instance démarrée/arrêtée à la demande** pour limiter les coûts.
- Le guide opérationnel est [AWS_EC2_GPU_DEPLOYMENT.md](AWS_EC2_GPU_DEPLOYMENT.md).
- **Aucune** dépendance à une API externe. Confidentialité totale. Compétence **Cloud & DevOps** démontrable.

---

## 15. Variables d'environnement (`.env.example`)

```env
# PostgreSQL
POSTGRES_USER=copilot
POSTGRES_PASSWORD=change_me
POSTGRES_DB=avaliance
DATABASE_URL=postgresql://copilot:change_me@postgres:5432/avaliance

# Backend Spring Boot
JWT_SECRET=change_me_long_random
IA_SERVICE_URL=http://service-ia:8000
INTERNAL_TOKEN=change_me_service_secret
DOCUMENT_STORAGE_PATH=/data/documents

# Service IA FastAPI
OLLAMA_URL=http://ollama:11434
LLM_MODEL=qwen3:8b
EMBEDDING_MODEL_PATH=BAAI/bge-m3
INTERNAL_TOKEN=change_me_service_secret

# Frontend
VITE_API_BASE_URL=http://localhost:8080/api
```

---

## 16. Plan d'exécution par phases (feuille de route officielle)

> Suis cet ordre. Chaque phase se termine par sa **Definition of Done (DoD)**. Ne passe à la phase suivante qu'une fois la DoD remplie.

### P0 — Préparation (S1)
- Créer l'arborescence (§7), `git init`, `docker-compose.yml`, `.env.example`, `README.md`.
- Lancer `postgres` + `ollama`, appliquer les migrations Flyway (§8), pull des modèles.
- Générer le corpus synthétique (§9).
- **Benchmark de latence** : valider le runtime GPU obligatoire et Ollama accéléré par GPU sur AWS EC2, en utilisant `LLM_MODEL=qwen3:8b`, `think:false`, `OLLAMA_NUM_CTX=8192` et `GENERATION_MAX_TOKENS=1500`.
- **DoD :** `docker compose up` démarre postgres+ollama ; schéma appliqué ; ≥300 missions générées ; latence locale et AWS mesurée ; tag exact `qwen3:8b` validé sans fallback.

### P1 — Fondations & intégration (S2)
- Squelette Spring Boot (Web, Security, JPA, PostgreSQL) + Spring Security JWT + endpoints auth.
- Squelette FastAPI avec `/health` et `/ready`; la readiness vérifie PostgreSQL, le modèle d'embeddings et le tag Ollama configuré.
- Valider l'appel **Spring Boot → FastAPI** en HTTP interne (avec `X-Internal-Token`).
- **DoD :** login retourne un JWT ; endpoint protégé accessible avec le token ; Spring Boot peut appeler `/health` de FastAPI.

### P2 — Ingestion & vectorisation (S3)
- Pipeline d'ingestion (chunking) + embeddings BGE-M3 + insertion pgvector 1024 dimensions + génération `tsvector` + schéma de tags.
- Introduire `corpus_scope` avec les valeurs `PDF`, `MISSION` et `LEGACY_SYNTHETIC`; la recherche de l'application doit utiliser `PDF` par défaut.
- Endpoint `/ingest` + endpoint de recherche basique.
- Registre `source_document`, stockage persistant des originaux et extraction sans OCR des PDF textuels, DOCX et TXT.
- Endpoint interne `/documents/ingest` avec remplacement atomique des chunks et conservation de la provenance.
- **DoD :** le corpus synthétique est indexé ; un document réel de chaque format supporté peut être stocké, extrait et indexé ; une recherche PDF-default renvoie des chunks avec la bonne provenance.

### P3 — RAG hybride (MVP) (S4–S5)
- Retrieval hybride en parallèle (vecteur + mots-clés via **RRF pondéré**) + cross-encoder BGE reranking + endpoint **missions similaires** (SQL). Ajouter `/retrieve/trace` pour l'audit de sélection et de latence.
- Génération via Ollama **avec citations, preuves et spans validés**, garde-fou anti-hallucination et SSE. Ne jamais confondre la validation de containment d'une quote avec la preuve d'entailment sémantique.
- Interface React : Search PDF-only streamée, annulable, avec mesure du premier token/durée, citations, aperçu des pages PDF et score.
- Administration React/Spring réservée aux ADMIN : upload 20 Mo, registre paginé, statuts, relance, téléchargement et suppression.
- Citations documentaires avec nom de fichier et page PDF optionnelle ; `missionId` reste nullable pour une source importée.
- **DoD :** depuis l'UI, une question PDF renvoie une réponse **sourcée** ; un document importé est retrouvable et cité ; l'annulation SSE est propre ; son original est téléchargeable à l'identique ; la relance et la suppression en cascade fonctionnent ; les missions similaires s'affichent ; le garde-fou se déclenche quand aucune source pertinente.

### P4 — Valeur ajoutée (ML & génération) (S6–S7)
- Préparer 60 000–100 000 triples `mMARCO-fr` et 5 000–10 000 paires/triples Avaliance-BOAMP, avec manifest de provenance/licences et splits par mission/document.
- Fine-tuning des embeddings sur Kaggle/Colab T4 avec un mélange cible 80/20.
- Charger BGE-M3 dans FastAPI via `EMBEDDING_MODEL_PATH=BAAI/bge-m3` et le cache Docker Hugging Face persistant.
- Génération de **structure RFP** à partir des missions similaires.
- Créer un golden dataset PDF versionné, **evaluation-only**, à partir de `source_document` et `doc_chunk` réellement indexés : questions, fragments attendus/interdits et spans exacts (document, SHA-256, chunk, page, quote). Ne jamais réparer le corpus pour satisfaire un ancien JSON non autoritatif.
- L'évaluateur doit appeler l'API publique authentifiée, mesurer retrieval/génération/total, vérifier citations et abstentions, et séparer les résultats de l'entraînement et du réglage.
- **DoD :** manifest dataset vérifiable ; absence de fuite entre splits ; modèle fine-tuné chargeable ; RFP structuré généré ; golden PDF reproductible et fondé sur la base en direct.

### P5 — Finalisation & déploiement (S8)
- Conteneurisation complète + déploiement sur **AWS EC2 `g4dn.xlarge`** avec Docker et NVIDIA Container Toolkit.
- Tests, documentation, `README` de démarrage, script de démo.
- **DoD :** `docker compose up` unique reproduit toute la démo ; l'app tourne sur la VM AWS avec Ollama accéléré par GPU ; README et `AWS_EC2_GPU_DEPLOYMENT.md` complets.

> **Priorisation en cas de contrainte de temps :** le banc d'évaluation + fine-tuning (P4) priment sur la génération RFP. La mesure de qualité est la principale valeur d'ingénierie différenciante.

---

## 17. Conventions de code & barre de qualité

- **Git :** commits atomiques, un par jalon, messages en anglais impératif (`feat: add hybrid retrieval endpoint`).
- **Java :** packages par domaine (§7), DTOs séparés des entités, Bean Validation, gestion d'erreurs centralisée (`@ControllerAdvice`).
- **Python :** typage Pydantic v2, `ruff`/`black` si dispo, fonctions pures pour retrieval/RRF, pas d'état global mutable.
- **TypeScript :** strict mode, composants fonctionnels, hooks, pas de `any` non justifié.
- **Secrets :** jamais commités ; via `.env` (fournir `.env.example`).
- **Tests :** au minimum auth (backend), RRF/retrieval/reranking, extraction/indexation, génération/preuves et Ollama (service-ia), ainsi qu'un test e2e des flux search SSE et document (upload, citation, téléchargement, suppression).
- **Évaluation :** toute affirmation de qualité doit citer une exécution du golden PDF fondé sur la base courante. Une citation textuellement valide ne suffit pas à déclarer une réponse sémantiquement correcte ou complète.
- **Logs & audit :** chaque requête métier journalisée.
- **Docs :** chaque service a un mini-README ; le README racine explique le démarrage complet.

---

## 18. Critères d'acceptation finaux (checklist)

- [ ] `docker compose up` démarre les 5 services sans erreur.
- [ ] Login JWT fonctionnel ; routes protégées.
- [ ] Corpus synthétique (≥300 missions) généré et indexé (pgvector + tsvector).
- [ ] Un ADMIN peut importer un PDF textuel, DOCX ou TXT de 20 Mo maximum ; un CONSULTANT ne peut pas administrer les documents.
- [ ] Les originaux sont conservés dans le volume `document_storage`, téléchargeables sans altération et associés à un SHA-256.
- [ ] Le registre expose les statuts `STORED`, `PROCESSING`, `INDEXED`, `FAILED`, les compteurs et les erreurs ; une indexation échouée peut être relancée.
- [ ] Recherche hybride PDF-default (vecteur + `tsvector` + RRF + cross-encoder reranker) opérationnelle avec filtres métadonnées et trace interne.
- [ ] Réponses **sourcées** avec citations de mission ou de document, nom du fichier, page PDF optionnelle, preuves/spans validés et score de confiance.
- [ ] Génération exclusivement avec `qwen3:8b`, `think:false`, contexte 8192 et maximum 1200 tokens ; aucun fallback LLM implicite.
- [ ] Garde-fou anti-hallucination actif, avec abstention canonique lorsqu'aucune preuve ne couvre la demande.
- [ ] La suppression d'un document retire l'original et ses chunks ; il ne ressort plus dans la recherche.
- [ ] Les PDF scannés/sans texte sont rejetés explicitement et aucun OCR n'est exécuté.
- [ ] Missions similaires (SQL) fonctionnelles.
- [ ] Génération de structure RFP.
- [ ] Dataset ML documenté : 60k–100k triples `mMARCO-fr`, 5k–10k exemples Avaliance-BOAMP, manifest licences/provenance et splits sans fuite.
- [ ] Golden PDF versionné, exclusivement évaluatif et vérifié contre les documents/chunks réellement indexés ; l'évaluateur contrôle réponse, abstention, citation exacte et latence.
- [ ] Aucun appel LLM externe ; tout auto-hébergé.
- [ ] README de démarrage complet + script de démo.
- [ ] (P5) Déployé sur AWS EC2 `g4dn.xlarge` via Docker avec GPU Ollama **et service-ia/reranker** vérifiés par `nvidia-smi`.

---

## 19. Non-goals (NE PAS construire dans le MVP)

Ces éléments appartiennent à la **roadmap future** (à présenter en vision de fin de soutenance uniquement) — **ne les code pas** :

- ❌ **Neo4j / GraphRAG complet** (extraction automatique d'entités/relations). Le besoin relationnel est couvert par les « missions similaires » en SQL léger.
- ❌ **Agents autonomes multi-LLM chaînés** (risque de latence multi-minutes sur CPU).
- ❌ **OCR et ingestion documentaire lourde** : pas de PDF scanné sans couche texte, ancien format `.doc`, PPTX, image, audio/vidéo ou emails avancés. Le périmètre supporté est strictement limité aux PDF textuels, DOCX et TXT de 20 Mo maximum.
- ❌ **Moteur de recommandation staffing (filtrage collaboratif)** — hors périmètre, non vérifiable sur données synthétiques. Seul un tag « profil référent » anonymisé est conservé comme métadonnée.

> Savoir **ne pas** sur-construire est un signal de maturité d'ingénierie. Justifie ces choix dans le README.

---

## 20. Gabarits de prompts LLM

**Sélection de preuves sourcée (`/generate`) :**
```
Tu es le contrôleur d'évidence d'Avaliance Copilot. Utilise UNIQUEMENT les extraits numérotés.
Retourne exclusivement le JSON suivant :
{"status":"SUPPORTED","evidence":[{"source":1,"quote":"Phrase exacte de l'extrait"}]}
ou
{"status":"NO_RELEVANT_EVIDENCE","evidence":[]}

Une réponse SUPPORTED n'est autorisée que si les quotes prouvent explicitement TOUS les éléments demandés.
Ne déduis, ne reformule et ne complète jamais une valeur. Vérifie l'attribut exact : budget engagé ≠ budget consommé ; architecture ≠ résultat ; cause ≠ impact.
Si un élément est absent ou ambigu, retourne NO_RELEVANT_EVIDENCE. Aucun Markdown, raisonnement, texte hors JSON ni balise <think>.

Question : {question}
Extraits :
{contexts_avec_identifiants}
JSON :
```

> La production doit ensuite transformer uniquement des preuves validées en prose française professionnelle et citer chaque affirmation. La validation actuelle de la présence textuelle d'une quote ne prouve pas encore l'entailment ni la couverture complète d'une question composée : cette limitation doit rester explicitement testée et mesurée.

**Génération de questions synthétiques (`generate_synthetic_pairs.py`) :**
```
À partir du document suivant, génère 2 à 3 questions réalistes qu'un consultant poserait et
auxquelles CE document répond directement. Une question par ligne, sans numérotation.

Document :
{document}
```

**Structure RFP (`/rfp`) :**
```
À partir des missions similaires ci-dessous, propose une STRUCTURE de proposition commerciale
(sections : Contexte, Compréhension du besoin, Approche/Architecture proposée, Stack technique,
Missions de référence comparables, Risques & mitigation, Planning indicatif).
Ne pas inventer de client réel. Rester générique et sourcé sur les missions fournies.

Missions similaires :
{missions}
```

---

## 21. Contenu attendu du `README.md` racine

1. Pitch du projet + problème résolu.
2. Architecture (schéma §5).
3. Prérequis (Docker, Docker Compose, compte AWS avec quota EC2 GPU, compte Colab pour le fine-tuning).
4. Démarrage local : `cp .env.example .env` → `docker compose up` → seed du corpus → accès UI.
5. Commandes utiles (Makefile : `up`, `down`, `seed`, `bench`, `finetune-eval`).
6. Résultats d'évaluation (tableau avant/après).
7. Formats documentaires supportés, limite de 20 Mo et workflow ADMIN (import, indexation, relance, téléchargement, suppression).
8. Stockage persistant des originaux, provenance des citations et politique explicite sans OCR.
9. Choix d'architecture & non-goals justifiés.
10. Déploiement AWS EC2 GPU documenté dans `AWS_EC2_GPU_DEPLOYMENT.md`.

---

### Fin de la skill. L'agent doit maintenant exécuter P0 → P5 dans l'ordre, en respectant les règles d'or (§2) et les non-goals (§19), jusqu'à la checklist d'acceptation (§18) complète.

The old JSON is not authoritative and may be inaccurate. Do not repair the production corpus to match it; replace the evaluation methodology with a new golden dataset grounded in the real PDFs currently indexed in PostgreSQL

---

## 22. État réel de la version actuelle (audit du 6 septembre 2026)

Cette section décrit le système tel qu'il existe réellement dans le dépôt à cette
date. Elle complète les sections de conception précédentes. Une capacité est
marquée « opérationnelle » lorsqu'elle existe dans le chemin d'exécution et qu'elle
possède des tests ciblés. Une capacité seulement décrite dans la roadmap reste à
construire.

### 22.1 Verdict exécutif

La version actuelle est un MVP RAG documentaire PDF solide et déjà structuré pour
une démonstration locale :

- React ne parle qu'au backend Spring Boot.
- Spring Boot porte l'authentification, les rôles, l'audit, le stockage original,
  le cycle de vie documentaire et l'orchestration.
- FastAPI est interne, stateless et protégé par `X-Internal-Token`.
- PostgreSQL/pgvector est la source de vérité des missions, chunks, embeddings,
  scopes et citations.
- Ollama est le seul moteur de génération et le modèle contractuel est exactement
  `qwen3:8b` avec `think:false`, `OLLAMA_NUM_CTX=8192` et une limite de 1500 tokens.
- Le retrieval de production est PDF-first : vector search + recherche française
  `tsvector`, fusion RRF pondérée, reranking cross-encoder, fenêtres de pages et
  conservation de l'évidence lexicale.
- La génération ne publie pas une preuve avant validation de la source, de la
  quote, de la citation et des spans.
- Le frontend fournit recherche SSE annulable, citations, prévisualisation PDF,
  administration des documents, missions, propositions RFP et utilisateurs.

Le système est donc fiable sur le flux documenté et sur les scénarios PDF couverts
par les tests. Il ne faut pas présenter cette version comme une précision sémantique
de 100 % sur n'importe quel PDF : la validation actuelle prouve principalement la
traçabilité et le containment textuel, pas l'entailment sémantique complet.

### 22.2 Architecture réellement déployée

Le `docker-compose.yml` courant contient cinq services :

| Service | Responsabilité actuelle | Exposition |
|---|---|---|
| `postgres` | PostgreSQL 16 + pgvector, migrations Flyway et données applicatives | réseau interne seulement |
| `ollama` | génération locale et warm-up du modèle exact configuré | réseau interne seulement |
| `service-ia` | extraction, embeddings BGE-M3, ingestion, retrieval, reranking, génération et RFP | réseau interne seulement |
| `backend` | API publique, JWT, autorisations, documents, audit et proxy IA | port 8080 |
| `frontend` | React compilé et servi par Nginx, proxy `/api` vers Spring Boot | port 3000 |

Les volumes nommés persistent PostgreSQL, modèles Ollama, cache Hugging Face et
originaux documentaires. FastAPI et Ollama n'ont pas de port publié vers le poste
client. Le GPU est demandé par défaut aux conteneurs Ollama et FastAPI ; le mode
CPU local doit donc être considéré comme une amélioration d'infrastructure à
finaliser, pas comme une garantie de cette configuration de base.

### 22.3 Flux complet d'une question RAG

1. L'utilisateur se connecte sur `/login`. Spring Security vérifie le JWT et
    distingue `ADMIN` de `CONSULTANT`.
2. La page Recherche envoie la question à `POST /api/search`. Le navigateur ne
    contacte ni FastAPI, ni PostgreSQL, ni Ollama.
3. `SearchService` ajoute l'identité de requête, écrit l'audit et appelle
    `IaClientService` avec le token interne.
4. FastAPI encode la requête avec BGE-M3 en 1024 dimensions.
5. PostgreSQL exécute en parallèle une recherche pgvector et une recherche
    française `tsvector`. Les deux listes sont fusionnées par RRF avec
    `1 / (60 + rang)` et les poids configurés.
6. Les candidats passent dans le cross-encoder `BAAI/bge-reranker-v2-m3`.
    Les résultats lexicaux forts, les meilleurs résultats vectoriels et les
    candidats RRF protégés restent dans le budget final.
7. Pour les PDF, la sélection conserve les chunks d'une même page et peut ajouter
    une continuation physique immédiate. Une question qui nomme un projet est
    limitée à sa famille documentaire lorsque celle-ci est identifiable.
8. `generate_sourced_answer` sélectionne les chunks utiles selon l'intention,
    transmet uniquement les extraits retenus à Ollama et demande une sortie
    structurée.
9. La réponse est contrôlée : index de source, document, page, quote exacte,
    citation, span et claims numériques doivent correspondre aux chunks réellement
    récupérés. Sinon le système renvoie une abstention ou un diagnostic explicite.
10. Spring Boot retransmet les événements SSE ; le frontend affiche le texte,
     les citations, la confiance, le diagnostic et les métriques de durée. Une
     annulation utilise `AbortController` et ferme le flux amont.

### 22.4 Retrieval : les protections réellement présentes

Le retrieval n'est pas un simple top-k vectoriel. Les protections actuelles sont :

- scope `PDF` par défaut et exclusion des sources `STORED`, `PROCESSING` ou
  `FAILED` ;
- séparation des scopes `PDF`, `MISSION` et `LEGACY_SYNTHETIC` ;
- embeddings BGE-M3 en dimension 1024 ;
- recherche plein texte française avec index GIN ;
- fusion RRF configurable et trace interne via `/retrieve/trace` ;
- reranking cross-encoder borné pour maîtriser la latence ;
- réserve d'évidence lexicale afin qu'un terme exact ne soit pas éliminé par le
  reranker ;
- sauvegarde des meilleurs rangs vectoriels/RRF ;
- conservation des chunks voisins d'une page et de la page suivante ;
- filtrage documentaire pour les projets explicitement nommés ;
- scores séparés : vectoriel, lexical, RRF, reranker et pertinence bornée ;
- traces de sélection et de latence utilisables par un évaluateur reproductible.

Les fonctions principales se trouvent dans `service-ia/app/retrieval/vector_search.py`
et les tests de non-régression dans `service-ia/tests/test_hybrid_retrieval.py`,
`test_retrieval_scope.py`, `test_retrieve.py` et `test_reranker.py`.

### 22.5 Ingestion et provenance

Le workflow ADMIN de `POST /api/documents` est le suivant : stockage de l'original,
SHA-256, statut, appel FastAPI multipart, extraction, chunking, embeddings et
remplacement transactionnel des chunks. Les extensions supportées sont PDF textuel,
DOCX et TXT, avec limite backend de 20 Mo et limite Nginx de 21 Mo par requête.

- PDF : extraction Docling sans OCR, fallback pypdf pour texte sélectionnable,
  conservation des pages physiques 1-based ;
- DOCX : paragraphes et tableaux conservés ;
- TXT : UTF-8/BOM puis fallback CP1252 ;
- PDF chiffré, vide, illisible ou scanné sans couche texte : rejet explicite ;
- suppression : original et chunks supprimés par cascade ;
- citation : `document_id`, nom, page optionnelle, chunk, score et request id ;
- relance : une source `FAILED` peut être réindexée sans perdre sa traçabilité.

Les migrations Flyway actuelles sont `V1` à `V7`. `V6` convertit la colonne
d'embedding vers la dimension BGE-M3 1024 ; cette migration est destructive pour
les anciens vecteurs et nécessite une réindexation complète après application.

### 22.6 Génération et garde-fou anti-hallucination

Tous les appels Ollama passent par `service-ia/app/generation/ollama.py` : modèle
configuré sans fallback implicite, `think:false`, température zéro, contexte borné,
`num_predict` borné et retry limité aux timeouts. La readiness échoue si le tag
exact n'existe pas ou si le warm-up ne répond pas.

La couche `service.py` combine :

- sortie JSON structurée ;
- validation des indices de sources et des citations ;
- containment de quote dans le texte source ;
- validation des offsets/spans et des claims numériques ;
- réponses extractives déterministes pour certains formats de tableaux et
  intentions fréquentes ;
- diagnostics `NO_RELEVANT_EVIDENCE`, `UNSUPPORTED_ANSWER` et
  `INVALID_CITATION_FORMAT` ;
- réponse canonique d'information insuffisante quand la preuve n'est pas sûre.

Cette conception est particulièrement forte pour empêcher une réponse non sourcée
de passer silencieusement. Elle ne doit cependant pas être décrite comme une preuve
d'entailment : une quote présente dans un chunk peut encore être insuffisante pour
répondre à toutes les sous-parties d'une question composée. Ce point est une limite
mesurée et doit rester visible dans toute soutenance ou évaluation.

### 22.7 RFP et traitements longs

Le flux RFP dispose de deux modes : réponse structurée synchrone et jobs durables
en PostgreSQL. Les jobs portent le propriétaire, le rôle, une lease renouvelable,
un nombre d'essais, une annulation et une rétention. Le worker récupère les jobs
après redémarrage et empêche qu'un consultant lise le résultat d'un autre utilisateur.

Le résultat RFP contient des sections, exigences, missions comparables, citations,
preuves, qualité et provenance. Les contrôles de qualité couvrent structure,
citations, isolation, réparation JSON, retries, fallback grounded et worker.

### 22.8 Frontend actuel

Les routes livrées sont : tableau de bord, recherche, propositions, missions,
détail mission, documents ADMIN et utilisateurs ADMIN. Les protections de route
existent à la fois dans React et côté Spring. La recherche est PDF-only, streamée,
annulable et affiche premier token, durée, citations et abstention. L'administration
permet drag-and-drop, validation 20 Mo, pagination, statuts, retry, téléchargement
et confirmation de suppression.

### 22.9 Matrice de maturité honnête

| Domaine | État actuel | Preuve ou remarque |
|---|---|---|
| Auth JWT et rôles | opérationnel | filtres Spring, routes protégées, tests backend |
| Proxy frontend -> backend -> IA | opérationnel | `IaClientService`, token interne, aucun accès direct du navigateur |
| Ingestion PDF/DOCX/TXT | opérationnel | extracteurs, provenance et tests ciblés |
| PostgreSQL + pgvector + tsvector | opérationnel | Flyway V1-V7, HNSW, dimension 1024 |
| Hybrid retrieval PDF | opérationnel | RRF, reranker, réserves lexicales, trace et tests |
| Citations et anti-hallucination | opérationnel avec limite connue | containment/spans validés ; entailment non complet |
| SSE et annulation | opérationnel | backend WebClient, Nginx no-buffer, AbortController |
| Similar missions | opérationnel | SQL + similarité sémantique sur corpus mission |
| RFP structuré et jobs | opérationnel | sections, leases, isolation, qualité et retry |
| Corpus synthétique | présent | générateur et manifest présents ; seed live à vérifier par environnement |
| Golden PDF fondé sur PostgreSQL live | à refaire | `benchmarks/rag-final.json` est ancien et non autoritatif |
| Fine-tuning ML mMARCO/BOAMP | à construire | répertoire `ml/` et artefacts annoncés absents |
| Déploiement CPU local garanti | à renforcer | compose/image actuels demandent GPU par défaut |
| README racine et guide AWS | à compléter | les README backend/frontend existent, pas le guide racine attendu |

### 22.10 Ce que signifie « RAG proche de 100 % »

La cible réaliste n'est pas d'afficher artificiellement `100 %`. La qualité doit
être démontrée séparément sur quatre axes :

1. **Retrieval** : le bon document, la bonne page et les bons chunks entrent dans
    le contexte ;
2. **Grounding** : chaque affirmation publiée possède une preuve et une citation ;
3. **Coverage** : toutes les sous-questions de la demande sont couvertes, ou le
    système s'abstient ;
4. **Robustesse** : absence de fuite entre utilisateurs, documents ou projets,
    avec latence et erreurs mesurées.

La méthode correcte pour l'atteindre est de générer un golden PDF exclusivement à
partir de `source_document` et `doc_chunk` présents dans la base live : pour chaque
cas, enregistrer SHA-256, document, page, chunk, quote exacte, fragments attendus,
fragments interdits et règle d'abstention. L'ancien `benchmarks/rag-final.json`, qui
référence `Avaliance_Questions_Reponses_Claires.md` et affiche des scores faibles,
ne doit ni piloter le corpus ni être utilisé comme preuve finale.

### 22.11 Priorités d'amélioration

1. Générer et versionner le golden PDF depuis PostgreSQL live, puis publier un
    rapport retrieval/generation/citation/abstention avec latence.
2. Remplacer les hypothèses propres à certains documents par des règles génériques
    de navigation de pages et de tables ; garder les heuristiques connues derrière
    des tests de régression explicites.
3. Ajouter la couverture de sous-questions et une validation sémantique mesurée,
    sans présenter le simple containment comme de l'entailment.
4. Fournir un override CPU reproductible et documenter séparément la cible GPU.
5. Ajouter les artefacts ML réellement promis : provenance/licences, splits sans
    fuite, notebook de fine-tuning et modèle chargeable.
6. Compléter le README racine, le guide AWS et les commandes Makefile réellement
    disponibles.

Ces priorités renforcent les points forts actuels sans fragiliser les contrats
publics : PDF par défaut, provenance stricte, modèle `qwen3:8b`, confidentialité,
abstention et séparation frontend/backend/IA restent non négociables.

### 22.12 Lecture de la capture du Dashboard

La capture fournie montre une preuve visuelle importante de la maturité opérationnelle
du produit :

- `107` missions capitalisées sur `5` secteurs ;
- `3 767` opérations sur les `30` derniers jours ;
- `4 495` recherches affichées dans le contexte d'activité ;
- `98,1 %` de taux de réussite et `80` erreurs ;
- `18,8 s` de temps de réponse moyen ;
- une activité séparée entre recherche, similarité et proposition ;
- une ventilation du corpus par secteurs et types d'intervention.

Le point essentiel est la définition technique de ce KPI. Le backend calcule le
`successRate` dans `DashboardService` avec :

```text
successRate = audit_log.successes / audit_log.total * 100
```

Le taux `98,1 %` signifie donc : **98,1 % des opérations auditées ont terminé sans
erreur technique** sur la période affichée. C'est une très bonne preuve de
stabilité du produit, de disponibilité du pipeline et de qualité de l'orchestration
Spring Boot -> FastAPI -> PostgreSQL/Ollama.

Il ne faut pas le reformuler automatiquement comme : « le modèle répond correctement
à 98,1 % des questions ». Une opération peut être techniquement réussie tout en
retournant une abstention correcte, une réponse partiellement couverte ou une
réponse dont la qualité sémantique doit encore être évaluée. La capture prouve donc
la **fiabilité opérationnelle**, pas à elle seule la **précision RAG**.

Pour annoncer honnêtement que le modèle répond correctement à environ 98 % des
questions, il faut un second KPI calculé par un évaluateur golden indépendant, avec
au minimum :

1. une liste de questions issues des PDF réellement indexés ;
2. les documents, pages, chunks et quotes attendus ;
3. une règle séparée pour les questions qui doivent produire une abstention ;
4. une vérification de retrieval, de citation, de couverture des sous-questions et
    d'exactitude factuelle ;
5. le dénominateur exact, le nombre de cas réussis et les erreurs détaillées.

Le message de soutenance recommandé est donc : **« Le Dashboard montre 98,1 % de
succès opérationnel sur les requêtes auditées. La précision des réponses RAG est
mesurée séparément par le golden PDF et ne doit pas être déduite de ce KPI. »**

Cette distinction renforce la crédibilité du projet : elle met en valeur le point
fort réel de l'application, à savoir un pipeline stable, traçable et sourcé, tout
en évitant de présenter un indicateur de disponibilité comme une mesure de vérité
du modèle.
