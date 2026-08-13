package com.avaliance.copilot.dashboard.dto;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;

public record DashboardSummary(
        OffsetDateTime generatedAt,
        int periodDays,
        long missionTotal,
        List<Breakdown> missionsBySector,
        List<Breakdown> missionsByType,
        List<YearMetric> missionsByYear,
        long userTotal,
        long adminCount,
        long consultantCount,
        ActivityMetrics activity,
        List<DailyMetric> dailyActivity,
        List<RecentEvent> recentActivity
) {
    public record Breakdown(String label, long total) {
    }

    public record YearMetric(int year, long total) {
    }

    public record ActivityMetrics(
            long total,
            long searches,
            long similarities,
            long rfpGenerations,
            long successes,
            long errors,
            double successRate,
            double averageDurationMs
    ) {
    }

    public record DailyMetric(LocalDate day, long total, long errors) {
    }

    public record RecentEvent(String action, String status, Long durationMs, OffsetDateTime createdAt) {
    }
}