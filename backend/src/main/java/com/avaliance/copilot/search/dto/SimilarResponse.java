package com.avaliance.copilot.search.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Response body for POST /api/similar — list of similar missions.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SimilarResponse {

    private List<SimilarMission> missions;

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class SimilarMission {
        private Long id;
        private String title;
        private String sector;
        private String missionType;
        private String[] technologies;
        private Integer year;
        private String summary;
        private Double similarityScore;
    }
}
