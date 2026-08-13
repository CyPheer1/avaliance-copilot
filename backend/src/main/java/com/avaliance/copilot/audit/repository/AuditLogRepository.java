package com.avaliance.copilot.audit.repository;

import com.avaliance.copilot.audit.entity.AuditLog;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;

@Repository
public interface AuditLogRepository extends JpaRepository<AuditLog, Long> {

	interface AuditSummaryProjection {
		Long getTotal();
		Long getSuccesses();
		Long getErrors();
		Double getAverageDurationMs();
	}

	interface LabelCountProjection {
		String getLabel();
		Long getTotal();
	}

	interface DailyActivityProjection {
		LocalDate getDay();
		Long getTotal();
		Long getErrors();
	}

	@Query(value = """
			SELECT COUNT(*) AS total,
				   SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS successes,
				   SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END) AS errors,
				   COALESCE(AVG(duration_ms), 0) AS averageDurationMs
			FROM audit_log
			WHERE created_at >= :since
			""", nativeQuery = true)
	AuditSummaryProjection summarizeSince(@Param("since") OffsetDateTime since);

	@Query(value = """
			SELECT action AS label, COUNT(*) AS total
			FROM audit_log
			WHERE created_at >= :since
			GROUP BY action
			ORDER BY total DESC
			""", nativeQuery = true)
	List<LabelCountProjection> countActionsSince(@Param("since") OffsetDateTime since);

	@Query(value = """
			SELECT (created_at AT TIME ZONE 'UTC')::date AS day,
				   COUNT(*) AS total,
				   SUM(CASE WHEN status = 'ERROR' THEN 1 ELSE 0 END) AS errors
			FROM audit_log
			WHERE created_at >= :since
			GROUP BY day
			ORDER BY day
			""", nativeQuery = true)
	List<DailyActivityProjection> countDailySince(@Param("since") OffsetDateTime since);

	List<AuditLog> findTop6ByCreatedAtGreaterThanEqualOrderByCreatedAtDesc(OffsetDateTime since);
}
