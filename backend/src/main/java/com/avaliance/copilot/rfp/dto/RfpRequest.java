package com.avaliance.copilot.rfp.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Request body for POST /api/rfp/generate.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class RfpRequest {

    @NotBlank(message = "Description is required")
    private String description;

    /** Optional sector filter for finding similar missions */
    private String sector;

    /** Optional mission type filter */
    private String missionType;

    /** Number of similar missions to base the RFP on */
    private Integer topK;
}
