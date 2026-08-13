-- =============================================================================
-- Avaliance Copilot — Database-Level Prerequisites
-- =============================================================================
-- This script runs ONCE when PostgreSQL initializes a fresh data directory.
-- It creates only the pgvector extension (a superuser operation).
--
-- SCHEMA OWNERSHIP DECISION:
-- All application tables, indexes and migrations are managed exclusively by
-- Flyway (backend/src/main/resources/db/migration/V1__schema.sql).
-- This init script intentionally does NOT create tables to avoid duplicate DDL
-- when Flyway runs on the same fresh database.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
