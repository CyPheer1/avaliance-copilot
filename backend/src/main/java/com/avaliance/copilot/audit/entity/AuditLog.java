package com.avaliance.copilot.audit.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.OffsetDateTime;

/**
 * JPA entity mapped to the "audit_log" table.
 * Records each business request for traceability.
 */
@Entity
@Table(name = "audit_log")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class AuditLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id")
    private Long userId;

    @Column(nullable = false)
    private String action; // SEARCH | GENERATE_RFP | SIMILAR

    @Column(name = "query_text")
    private String queryText;

    @Column(nullable = false)
    private String status; // SUCCESS | ERROR

    @Column(name = "duration_ms")
    private Long durationMs;

    @Column(name = "created_at", insertable = false, updatable = false)
    private OffsetDateTime createdAt;
}
