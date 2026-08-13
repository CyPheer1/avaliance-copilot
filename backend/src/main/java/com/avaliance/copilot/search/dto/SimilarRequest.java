package com.avaliance.copilot.search.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Request body for POST /api/similar.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class SimilarRequest {

    @NotBlank(message = "Description is required")
    private String description;

    /** Optional sector filter */
    private String sector;

    /** Optional mission type filter */
    private String missionType;

    /** Number of similar missions to return */
    private Integer topK;
}
