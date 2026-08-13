package com.avaliance.copilot.integration;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Validates that Flyway successfully applies V1__schema.sql to a real PostgreSQL+pgvector instance.
 */
class FlywaySchemaIT extends AbstractIntegrationTest {

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    @DisplayName("Flyway schema is applied and vector extension exists")
    void schemaAppliedSuccessfully() {
        // Verify vector extension
        Integer extCount = jdbcTemplate.queryForObject(
                "SELECT count(*) FROM pg_extension WHERE extname = 'vector'", Integer.class);
        assertThat(extCount).isEqualTo(1);

        // Verify tables exist
        Integer tableCount = jdbcTemplate.queryForObject(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' " +
                        "AND table_name IN ('mission', 'doc_chunk', 'app_user', 'audit_log')", Integer.class);
        assertThat(tableCount).isEqualTo(4);

        // Verify specific columns (e.g. vector, tsvector, text[])
        String docChunkVectorType = jdbcTemplate.queryForObject(
                "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a " +
                        "JOIN pg_class c ON c.oid = a.attrelid " +
                        "WHERE c.relname = 'doc_chunk' AND a.attname = 'embedding'", String.class);
        assertThat(docChunkVectorType).isEqualTo("vector(1024)");

        String missionTechType = jdbcTemplate.queryForObject(
                "SELECT data_type FROM information_schema.columns WHERE table_name = 'mission' AND column_name = 'technologies'", String.class);
        assertThat(missionTechType).isEqualTo("ARRAY"); // text[]

        Integer hnswIndexCount = jdbcTemplate.queryForObject(
                "SELECT count(*) FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'doc_chunk' " +
                        "AND indexdef ILIKE '%USING hnsw%'", Integer.class);
        assertThat(hnswIndexCount).isEqualTo(1);

        Integer ginIndexCount = jdbcTemplate.queryForObject(
                "SELECT count(*) FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'doc_chunk' " +
                        "AND indexdef ILIKE '%USING gin%'", Integer.class);
        assertThat(ginIndexCount).isEqualTo(1);
    }
}
