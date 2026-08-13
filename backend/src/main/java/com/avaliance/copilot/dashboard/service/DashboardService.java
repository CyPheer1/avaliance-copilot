package com.avaliance.copilot.dashboard.service;

import com.avaliance.copilot.audit.entity.AuditLog;
import com.avaliance.copilot.audit.repository.AuditLogRepository;
import com.avaliance.copilot.auth.repository.AppUserRepository;
import com.avaliance.copilot.dashboard.dto.DashboardSummary;
import com.avaliance.copilot.mission.repository.MissionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

@Service
@RequiredArgsConstructor
public class DashboardService {

    private final MissionRepository missionRepository;
    private final AppUserRepository appUserRepository;
    private final AuditLogRepository auditLogRepository;

    @Transactional(readOnly = true)
    public DashboardSummary getSummary(int requestedDays) {
        int periodDays = Math.max(7, Math.min(requestedDays, 90));
        OffsetDateTime generatedAt = OffsetDateTime.now(ZoneOffset.UTC);
        OffsetDateTime since = generatedAt.minusDays(periodDays - 1L).toLocalDate().atStartOfDay().atOffset(ZoneOffset.UTC);

        AuditLogRepository.AuditSummaryProjection audit = auditLogRepository.summarizeSince(since);
        Map<String, Long> actionCounts = auditLogRepository.countActionsSince(since).stream()
                .collect(Collectors.toMap(AuditLogRepository.LabelCountProjection::getLabel, DashboardService::total));
        Map<LocalDate, AuditLogRepository.DailyActivityProjection> dailyCounts = auditLogRepository.countDailySince(since).stream()
                .collect(Collectors.toMap(AuditLogRepository.DailyActivityProjection::getDay, Function.identity()));

        long activityTotal = value(audit.getTotal());
        long successes = value(audit.getSuccesses());
        long errors = value(audit.getErrors());
        double successRate = activityTotal == 0 ? 0 : successes * 100.0 / activityTotal;

        DashboardSummary.ActivityMetrics activity = new DashboardSummary.ActivityMetrics(
                activityTotal,
                actionCounts.getOrDefault("SEARCH", 0L),
                actionCounts.getOrDefault("SIMILAR", 0L),
                actionCounts.getOrDefault("GENERATE_RFP", 0L),
                successes,
                errors,
                round(successRate),
                round(audit.getAverageDurationMs() == null ? 0 : audit.getAverageDurationMs())
        );

        LocalDate firstDay = since.toLocalDate();
        List<DashboardSummary.DailyMetric> dailyActivity = IntStream.range(0, periodDays)
                .mapToObj(offset -> firstDay.plusDays(offset))
                .map(day -> {
                    AuditLogRepository.DailyActivityProjection metric = dailyCounts.get(day);
                    return new DashboardSummary.DailyMetric(day, metric == null ? 0 : total(metric), metric == null ? 0 : value(metric.getErrors()));
                })
                .toList();

        return new DashboardSummary(
                generatedAt,
                periodDays,
                missionRepository.count(),
                missionRepository.countBySector().stream().map(metric -> new DashboardSummary.Breakdown(metric.getLabel(), total(metric))).toList(),
                missionRepository.countByMissionType().stream().map(metric -> new DashboardSummary.Breakdown(metric.getLabel(), total(metric))).toList(),
                missionRepository.countByYear().stream().map(metric -> new DashboardSummary.YearMetric(metric.getYear(), value(metric.getTotal()))).toList(),
                appUserRepository.count(),
                appUserRepository.countByRole("ADMIN"),
                appUserRepository.countByRole("CONSULTANT"),
                activity,
                dailyActivity,
                auditLogRepository.findTop6ByCreatedAtGreaterThanEqualOrderByCreatedAtDesc(since).stream().map(DashboardService::recentEvent).toList()
        );
    }

    private static DashboardSummary.RecentEvent recentEvent(AuditLog log) {
        return new DashboardSummary.RecentEvent(log.getAction(), log.getStatus(), log.getDurationMs(), log.getCreatedAt());
    }

    private static long total(AuditLogRepository.LabelCountProjection metric) {
        return value(metric.getTotal());
    }

    private static long total(AuditLogRepository.DailyActivityProjection metric) {
        return value(metric.getTotal());
    }

    private static long total(MissionRepository.LabelCountProjection metric) {
        return value(metric.getTotal());
    }

    private static long value(Long number) {
        return number == null ? 0 : number;
    }

    private static double round(double number) {
        return Math.round(number * 10.0) / 10.0;
    }
}