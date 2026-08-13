package com.avaliance.copilot.search.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Response body for POST /api/search — contains the generated answer,
 * citations, and confidence score.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class SearchResponse {

    /** Generated answer text (sourced, in French) */
    private String answer;

    /** Source citations referenced in the answer */
    private List<Citation> citations;

    /** Confidence score (0.0–1.0) */
    private Double confidence;

    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class Citation {
        private String citationId;
        private String requestId;
        private Long chunkId;
        private Long missionId;
        private String missionTitle;
        private Long documentId;
        private String documentName;
        private Integer page;
        private String corpusScope;
        private String content;
        private Double score;
        private Double rrfScore;
        private Double relevanceScore;
    }
}
