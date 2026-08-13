package com.avaliance.copilot.search.dto;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Request body for POST /api/search.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class SearchRequest {

    @NotBlank(message = "Query is required")
    private String query;

    /** Optional sector filter */
    private String sector;

    /** Optional mission type filter */
    private String missionType;

    /** Optional year filter */
    private Integer year;

    /** Number of top-k results (default handled by FastAPI) */
    private Integer topK;

    /** Retrieval scope, defaults to PDF for /recherche */
    private String corpusScope;

    /** Correlation id propagated through retrieval/generation */
    private String requestId;

    @AssertTrue(message = "Only PDF corpusScope is allowed on production search endpoints")
    public boolean isProductionCorpusScopeAllowed() {
        return corpusScope == null || corpusScope.isBlank() || "PDF".equalsIgnoreCase(corpusScope);
    }
}
