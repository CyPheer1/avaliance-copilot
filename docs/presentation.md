# Avaliance Copilot — Plateforme RAG souveraine d'intelligence documentaire

## Slide 1 : Avaliance Copilot — Le problème, la solution, et les choix fondateurs

**Visual Content:**
- **Problème :** Un patrimoine documentaire interne riche (PDF de missions, propositions, livrables) mais inexploitable rapidement par les consultants — la recherche manuelle dans les dossiers prend un temps considérable
- **Solution :** Plateforme RAG complète permettant deux parcours métier critiques — la **Recherche Documentaire sourcée** (Q&A avec citations et navigation PDF page exacte) et la **Génération automatique de Propositions Commerciales** (RFP structurées ancrées dans les vraies réussites d'Avaliance)
- **Choix fondateur : Zéro API externe.** Embedding (`BAAI/bge-m3` 1024d), Reranking (`BAAI/bge-reranker-v2-m3`) et Génération (`Qwen3:8b` via Ollama) — tout tourne en local sur GPU NVIDIA T4. Coût par requête : 0€. Aucune donnée ne quitte le réseau privé
- **Garantie anti-hallucination :** Chaque réponse est prouvée par citation exacte vérifiée programmatiquement, ou le système émet une abstention explicite : *« Information insuffisante dans le corpus pour répondre de manière fiable »*

**Speaker Notes:**
Avaliance Copilot résout le problème de la connaissance dispersée dans un cabinet de conseil. Les consultants passent un temps significatif à retrouver des informations dans des PDF de missions passées. La plateforme offre deux parcours métier : la Recherche Documentaire permet de poser une question en français naturel et d'obtenir une réponse sourcée avec navigation directe dans le PDF à la page exacte. La Génération RFP permet de soumettre un cahier des charges client et d'obtenir une proposition technique structurée en sections, ancrée dans les vraies réussites d'Avaliance. Le principe fondateur est le Zéro API externe : les données clients étant sous NDA et secret professionnel (banques, télécoms, administrations), toute la chaîne IA est auto-hébergée. Le modèle d'embedding BGE-M3 produit des vecteurs de 1024 dimensions sur CUDA float16, le cross-encoder BGE-Reranker-v2-M3 affine la pertinence, et le LLM Qwen3:8b génère les réponses — le tout sans aucun appel réseau externe.

---

## Slide 2 : Architecture — 5 services Docker orchestrés avec frontières de confiance

**Visual Content:**
- **Frontend** (React 18 / TypeScript / Vite → Nginx 1.27) : SPA avec PDF viewer intégré pour vérification des sources, proxy inverse `/api/` vers Spring Boot, `proxy_buffering off` pour le temps réel
- **Backend** (Spring Boot 3.3 / Java 17 / Maven) : API Gateway unique exposée sur le port 8080, JWT HS256 + BCrypt + RBAC (`ADMIN` uploade les documents / `CONSULTANT` recherche), Flyway pour les migrations SQL versionnées, audit log persistant de chaque opération
- **Service IA** (FastAPI / Python 3.11 / PyTorch 2.6 + CUDA 12.4) : Pipeline RAG complet — extraction Docling, chunking sémantique avec contextual retrieval, embedding BGE-M3, retrieval hybride vectoriel + lexical, reranking cross-encoder, génération Ollama avec validation d'évidence. Protégé par `X-Internal-Token` vérifié avec `secrets.compare_digest()` (temps constant, anti timing-attack)
- **Persistance** : PostgreSQL 16 + pgvector (index HNSW 1024d + tsvector français) · Ollama (Qwen3:8b résident GPU, `keep_alive=30m`) · 4 volumes Docker nommés : `pgdata`, `ollama_models`, `huggingface_cache`, `document_storage`

**Speaker Notes:**
L'architecture suit une chaîne de dépendance stricte avec health checks Docker : PostgreSQL doit passer `pg_isready` avant que le service IA démarre. Le service IA doit valider son endpoint `/ready` (qui vérifie que le modèle BGE-M3 est chargé sur GPU ET que Ollama a warmé le LLM) avec un `start_period` de 120 secondes et 10 retries. Spring Boot doit passer son Actuator `/health` avant que le frontend devienne accessible. Le frontend ne parle jamais directement au service IA ni à la base. La communication Spring–FastAPI passe par le réseau Docker bridge privé `avaliance-internal` : les ports PostgreSQL (5432), Ollama (11434) et FastAPI (8000) ne sont jamais exposés sur l'hôte. Chaque requête porte un `X-Request-Id` UUID propagé de React à Nginx à Spring Boot à FastAPI pour la traçabilité distribuée complète. Le backend Spring Boot tourne en tant qu'utilisateur non-root `appuser` avec les documents stockés dans un volume monté à `/data/documents`.

---

## Slide 3 : Pipeline d'ingestion — du PDF brut au chunk vectorisé

**Visual Content:**
- **Extraction structurée :** Docling (IBM, MIT-licensed) pour les PDF avec préservation des tableaux en Markdown structuré + pages physiques réelles ; python-docx pour DOCX ; fallback pypdf pour texte sélectionnable. Documents scannés sans texte exploitable refusés explicitement (pas de fausse précision)
- **Chunking sémantique :** Découpage par frontières phrase/paragraphe — cible ~850 caractères, minimum 250, recouvrement borné de 64 caractères (dernière phrase du chunk précédent propagée pour maintenir le contexte). Les frontières de pages PDF réelles sont conservées pour la navigation exacte
- **Contextual Retrieval (LLM-assisted) :** Pour chaque chunk, Ollama génère un préfixe contextuel de 50-100 mots (max 120 tokens) décrivant le rôle du chunk dans le document. Ce préfixe est concaténé au chunk **uniquement pour calculer l'embedding** — il n'est ni stocké ni affiché, préservant l'intégrité de la citation source. Dégradation gracieuse vers le chunk brut si Ollama est indisponible
- **Persistance transactionnelle :** `DELETE + INSERT` atomique dans `doc_chunk` — SHA-256 du fichier original, cycle de vie `STORED → PROCESSING → INDEXED / FAILED`, `corpus_scope = 'PDF'` pour isoler les documents administrés du corpus de démonstration

**Speaker Notes:**
L'ingestion est la fondation de la qualité du RAG. Docling est crucial car il préserve la structure des tableaux PDF en Markdown : un tableau financier reste un tableau avec colonnes et lignes, pas du texte aplati. Les pages physiques réelles sont conservées dans `source_page` pour permettre la navigation exacte dans le PDF original depuis l'interface. Le chunking est linguistiquement conscient : il découpe par paragraphe puis par phrase, avec un recouvrement borné. L'innovation technique clé est le Contextual Retrieval inspiré de la recherche Anthropic : au lieu d'indexer un chunk brut comme « la latence a diminué de 40% », le LLM génère un préfixe contextuel (« Ce paragraphe décrit les résultats du projet IoT Métrologie pour un client télécom ») qui enrichit l'embedding sans contaminer le texte source. Le tout est persisté avec `corpus_scope = 'PDF'` et le remplacement est toujours transactionnel pour éviter un index incohérent entre anciens et nouveaux chunks.

---

## Slide 4 : Recherche hybride — 5 étapes du sémantique au cross-encoder

**Visual Content:**
- **Étape 1 — Dual-branch parallèle :** Embedding BGE-M3 de la question → recherche vectorielle HNSW (`embedding <=> query::vector`, cosinus, `ef_search=100`, `iterative_scan=strict_order`) en parallèle avec Full-Text Search français (`ts_rank_cd`, dictionnaire unaccent, expansion de requête sectorielle automatique). Exécution concurrente via `ThreadPoolExecutor`
- **Étape 2 — Fusion RRF :** Reciprocal Rank Fusion : `score(d) = Σ weight_i / (k + rank_i)` avec `k=60`, poids vectoriel et textuel configurables. Boost projet nommé (+0.15) si la question mentionne un nom de projet spécifique (détection par regex et fuzzy-matching sur les noms de documents)
- **Étape 3 — Protection d'évidence :** Avant le reranking, les top-10 RRF + top-10 vectoriels + top-5 lexicaux forts sont sauvegardés comme IDs protégés — un mécanisme conçu spécifiquement pour empêcher le cross-encoder d'éliminer un passage bref mais décisif (un chiffre financier, un nom de responsable)
- **Étape 4 — Cross-Encoder :** `BAAI/bge-reranker-v2-m3` score chaque paire (question, chunk) conjointement via attention croisée complète du transformer — batch 16, CUDA float16, singleton avec `threading.Lock`. Appliqué uniquement au top-30 candidats pour maîtriser la latence
- **Étape 5 — Sélection finale (10-15 chunks) :** Coverage-aware selection avec page-sibling windows : si un tableau est découpé entre page 5 et page 6, les chunks adjacents sont récupérés automatiquement (requête SQL ciblée `source_document_id + source_page + 1`). Tri final par `chunk_index` physique pour la lisibilité

**Speaker Notes:**
La recherche hybride est le cœur technique du projet et sa plus grande contribution d'ingénierie. Les deux branches sont exécutées en parallèle pour minimiser la latence. La branche vectorielle utilise l'index HNSW de pgvector avec `iterative_scan = strict_order` qui garantit l'exactitude top-K. La branche lexicale utilise le tsvector PostgreSQL avec un dictionnaire français et une expansion de requête automatique : si un consultant demande « quelle est l'architecture technique ? », des termes comme « kafka », « kubernetes », « azure », « keycloak » sont ajoutés silencieusement. Le RRF fusionne les deux listes sans problème de normalisation. Le mécanisme de protection d'évidence est une innovation spécifique à ce corpus : dans les longs PDF de missions, le cross-encoder peut préférer un passage fluide mais vague à un passage bref mais contenant un chiffre ou un nom décisif. En protégeant les meilleurs candidats de chaque signal, on garantit qu'ils restent dans le contexte final. L'expansion par page-sibling est une requête SQL bornée qui récupère les chunks de la page suivante uniquement pour les documents source des ancres sélectionnées, évitant qu'un tableau soit coupé.

---

## Slide 5 : Génération RAG contrôlée — répondre seulement si c'est prouvable

**Visual Content:**
- **Prompt strict français :** Les chunks numérotés `[1]...[N]` sont injectés dans un prompt qui exige un JSON structuré : `{"status": "SUPPORTED"|"NO_RELEVANT_EVIDENCE", "answer": "...", "coverage": [{"criterion": "...", "evidence": [{"source": N, "quote": "extrait exact"}]}]}`
- **Contraintes Ollama :** Modèle Qwen3:8b, température 0, `think: false` (suppression des blocs `<think>`), contexte 8192 tokens, max 1500 tokens de sortie. Schéma JSON imposé via le paramètre `format` d'Ollama — contrainte au niveau grammaire, pas au niveau prompt
- **3 verrous de validation post-génération :** (1) Chaque `quote` est vérifiée mot à mot dans le chunk source via `SequenceMatcher` (2) La provenance complète (document_id + page) est validée (3) Si vérification échoue → **3 niveaux de fallback** : parsing alternatif → fallback extractif pur (phrases extraites directement du corpus sans reformulation) → abstention standardisée
- **Résultat :** Le LLM ne décide jamais seul de ce qui est vrai. Les tokens provisoires sont toujours bufferisés jusqu'à validation complète. Si la validation échoue, l'utilisateur reçoit le message d'abstention, jamais les tokens non vérifiés

**Speaker Notes:**
La génération est l'étape la plus critique et la plus différenciante du projet. Le LLM ne reçoit jamais les documents complets, seulement un catalogue de chunks numérotés et immuables. Il doit produire un JSON structuré avec des citations par critère atomique, chaque citation contenant un extrait exact copié mot à mot du chunk source. Le schéma JSON est imposé au niveau du serveur Ollama via le paramètre `format` qui contraint la grammaire de sortie — pas un simple prompt engineering. Après la génération, le service Python vérifie programmatiquement que chaque quote existe réellement dans le chunk déclaré. Si la vérification échoue, trois niveaux de fallback s'enchaînent automatiquement : tentative de parsing alternatif, puis fallback extractif pur qui extrait directement des phrases du corpus sans aucune reformulation (donc provenance garantie par construction), puis abstention standardisée. Le point crucial est que les tokens du modèle ne sont JAMAIS envoyés au navigateur avant validation complète. Si la validation échoue, l'utilisateur reçoit uniquement le message d'abstention — il ne verra jamais une réponse non prouvée. C'est cette garantie qui rend le système utilisable dans un contexte professionnel où citer un chiffre erroné dans une proposition pourrait avoir des conséquences significatives.

---

## Slide 6 : Déploiement sur AWS — Infrastructure GPU reproductible

**Visual Content:**
- **Instance cible :** AWS EC2 `g4dn.xlarge` — 4 vCPU, 16 Go RAM, 1 GPU NVIDIA T4 (16 Go VRAM), Ubuntu 24.04 LTS, Docker Engine + NVIDIA Container Toolkit installé
- **5 conteneurs Docker Compose** avec chaîne de démarrage séquentielle par health checks :
  `PostgreSQL 16 (pgvector)` ✅ → `Ollama (qwen3:8b sur GPU)` ✅ → `Service IA (PyTorch 2.6 CUDA 12.4)` ✅ → `Spring Boot 3.3 (Java 17)` ✅ → `React/Nginx 1.27` ✅
- **4 volumes Docker nommés persistants :**
  `avaliance_pgdata` (données PostgreSQL) · `avaliance_ollama_models` (poids LLM ~5 Go) · `avaliance_huggingface_cache` (BGE-M3 + Reranker ~2.5 Go) · `avaliance_document_storage` (fichiers PDF/DOCX originaux)
- **Réseau & sécurité :** Bridge Docker privé `avaliance-internal` — seuls les ports `8080` (API) et `3000` (UI) sont exposés sur l'hôte. PostgreSQL (5432), Ollama (11434) et FastAPI (8000) restent strictement internes. Tous les conteneurs tournent en utilisateur non-root (`appuser`)

**Speaker Notes:**
Le déploiement est conçu pour être 100% reproductible avec une seule commande : `cp .env.example .env && docker compose up -d --build`. L'instance AWS g4dn.xlarge a été choisie car c'est le meilleur rapport qualité/prix pour de l'inférence GPU chez AWS : la carte NVIDIA T4 offre 16 Go de VRAM en float16, suffisants pour charger simultanément le LLM Qwen3:8b (~5 Go), le modèle d'embedding BGE-M3 (~1.2 Go) et le cross-encoder reranker (~1.1 Go). Le GPU est partagé entre le conteneur Ollama et le service IA via `gpus: all` et les variables `NVIDIA_VISIBLE_DEVICES=all`. La chaîne de health checks garantit qu'aucun service ne reçoit de trafic avant que ses dépendances soient pleinement opérationnelles : le service IA a un `start_period` de 120 secondes avec 10 retries pour laisser le temps au téléchargement initial des modèles HuggingFace et au warmup Ollama. Les 4 volumes nommés permettent de recréer les conteneurs sans perte de données : les poids des modèles, les documents originaux et la base PostgreSQL survivent aux redéploiements. Le fichier `.env.example` documente les 40+ variables de configuration avec des valeurs par défaut sûres pour le développement et des placeholders explicites `change_me_*` pour la production. Les images Docker utilisent un build multi-stage : le backend Maven compile en `maven:3.9-eclipse-temurin-17` puis s'exécute sur `eclipse-temurin:17-jre-alpine`, le frontend Vite build en `node:22-alpine` puis se sert via `nginx:1.27-alpine`, et le service IA part de `pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime` pour le support CUDA natif.
