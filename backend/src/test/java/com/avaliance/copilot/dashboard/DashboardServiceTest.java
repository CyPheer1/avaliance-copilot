package com.avaliance.copilot.dashboard;

import com.avaliance.copilot.audit.repository.AuditLogRepository;
import com.avaliance.copilot.auth.repository.AppUserRepository;
import com.avaliance.copilot.dashboard.dto.DashboardSummary;
import com.avaliance.copilot.dashboard.service.DashboardService;
import com.avaliance.copilot.mission.repository.MissionRepository;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class DashboardServiceTest {

    @Mock
    private MissionRepository missionRepository;

    @Mock
    private AppUserRepository appUserRepository;

    @Mock
    private AuditLogRepository auditLogRepository;

    @Test
    void getSummary_calculatesMetricsAndFillsEmptyDays() {
        AuditLogRepository.AuditSummaryProjection audit = mock(AuditLogRepository.AuditSummaryProjection.class);
        AuditLogRepository.LabelCountProjection searches = labelCount("SEARCH", 3L);
        AuditLogRepository.LabelCountProjection rfp = labelCount("GENERATE_RFP", 1L);
        MissionRepository.LabelCountProjection sector = mock(MissionRepository.LabelCountProjection.class);

        when(audit.getTotal()).thenReturn(4L);
        when(audit.getSuccesses()).thenReturn(3L);
        when(audit.getErrors()).thenReturn(1L);
        when(audit.getAverageDurationMs()).thenReturn(245.55);
        when(auditLogRepository.summarizeSince(any())).thenReturn(audit);
        when(auditLogRepository.countActionsSince(any())).thenReturn(List.of(searches, rfp));
        when(auditLogRepository.countDailySince(any())).thenReturn(List.of());
        when(auditLogRepository.findTop6ByCreatedAtGreaterThanEqualOrderByCreatedAtDesc(any())).thenReturn(List.of());
        when(missionRepository.count()).thenReturn(12L);
        when(sector.getLabel()).thenReturn("Banque");
        when(sector.getTotal()).thenReturn(7L);
        when(missionRepository.countBySector()).thenReturn(List.of(sector));
        when(missionRepository.countByMissionType()).thenReturn(List.of());
        when(missionRepository.countByYear()).thenReturn(List.of());
        when(appUserRepository.count()).thenReturn(5L);
        when(appUserRepository.countByRole("ADMIN")).thenReturn(2L);
        when(appUserRepository.countByRole("CONSULTANT")).thenReturn(3L);

        DashboardSummary result = new DashboardService(missionRepository, appUserRepository, auditLogRepository).getSummary(3);

        assertThat(result.periodDays()).isEqualTo(7);
        assertThat(result.dailyActivity()).hasSize(7).allMatch(day -> day.total() == 0);
        assertThat(result.missionTotal()).isEqualTo(12);
        assertThat(result.missionsBySector()).containsExactly(new DashboardSummary.Breakdown("Banque", 7));
        assertThat(result.userTotal()).isEqualTo(5);
        assertThat(result.activity().searches()).isEqualTo(3);
        assertThat(result.activity().rfpGenerations()).isEqualTo(1);
        assertThat(result.activity().successRate()).isEqualTo(75.0);
        assertThat(result.activity().averageDurationMs()).isEqualTo(245.6);
    }

    private static AuditLogRepository.LabelCountProjection labelCount(String label, Long total) {
        AuditLogRepository.LabelCountProjection metric = mock(AuditLogRepository.LabelCountProjection.class);
        when(metric.getLabel()).thenReturn(label);
        when(metric.getTotal()).thenReturn(total);
        return metric;
    }
}