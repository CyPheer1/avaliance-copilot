# Avaliance Copilot — Backend (Spring Boot 3)

Backend principal du projet Avaliance Copilot. Fournit l'authentification JWT, la gestion des missions, l'orchestration des appels vers le service IA (FastAPI), l'audit et l'API REST consommée par le frontend React.

## Stack & Sécurité
- **Java 17** + **Spring Boot 3.3.7** + **Maven**
- **Sécurité** : JWT HS256 (clé > 64 chars obligatoire), Spring Security
- **Base de données** : PostgreSQL 16 + pgvector (géré via **Flyway**)
- **Client IA** : RestClient avec timeouts configurables et mode "Stub"
- **Documentation** : OpenAPI (Swagger UI) via `springdoc`

> ⚠️ **Aucune lib IA/ML côté Java.** Toute la logique IA est dans le service FastAPI.

## Démarrage Rapide (Dev)

Un fichier `docker-compose.dev.yml` est fourni pour lancer rapidement la base de données requise :

1. Copier le fichier d'environnement :
   ```bash
   cp .env.example .env
   # Modifier .env si nécessaire (les valeurs par défaut de l'example suffisent pour dev)
   ```

2. Lancer la base de données avec pgvector :
   ```bash
   docker compose -f docker-compose.dev.yml up -d postgres
   ```

3. Lancer le backend (utilise H2 en test, PostgreSQL en exécution normale) :
   ```bash
   # L'utilisateur ADMIN est automatiquement créé au démarrage via les variables ADMIN_USERNAME / ADMIN_PASSWORD
   ./mvnw spring-boot:run
   ```

## Swagger UI / OpenAPI
Une fois lancé, la documentation interactive de l'API est disponible ici :
- **Swagger UI** : `http://localhost:8080/swagger-ui.html`
- **OpenAPI JSON** : `http://localhost:8080/v3/api-docs`

## Variables d'environnement Obligatoires

L'application **refusera de démarrer** (fail-fast) si ces variables critiques sont absentes :
- `JWT_SECRET` (doit faire au moins 64 caractères)
- `INTERNAL_TOKEN` (pour communiquer avec FastAPI)
- `ADMIN_USERNAME` et `ADMIN_PASSWORD` (pour créer le premier admin)
- `DB_PASSWORD`

Voir le fichier `.env.example` pour la liste complète.

## Architecture & Choix techniques

1. **Flyway** : Gère le schéma complet (`V1__schema.sql`) incluant l'extension `vector`, les index HNSW et `tsvector`.
2. **Mode Stub (`IA_STUB_ENABLED=true`)** : Permet au backend de fonctionner seul en renvoyant des réponses bouchonnées pour les routes IA sans nécessiter que FastAPI tourne.
3. **Timeouts IA** : `IA_CONNECT_TIMEOUT_MS` (défaut 5s) et `IA_READ_TIMEOUT_MS` (défaut 120s, pour tolérer la génération LLM lente). Si échec, renvoie `503 Service Unavailable`.
4. **Audit** : Toute requête métier (SEARCH, SIMILAR, GENERATE_RFP) est loggée dans `audit_log` avec son statut (SUCCESS/ERROR) et sa durée d'exécution (ms).

## Tests

L'application contient des tests unitaires rapides (base H2 en mémoire, Flyway désactivé) et des tests d'intégration avec **Testcontainers** (lance un vrai PostgreSQL+pgvector sous Docker pour valider Flyway et les requêtes complexes).

```bash
# Lancer les tests unitaires ET d'intégration
./mvnw verify
```
