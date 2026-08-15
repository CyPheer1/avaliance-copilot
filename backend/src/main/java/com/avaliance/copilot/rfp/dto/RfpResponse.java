package com.avaliance.copilot.rfp.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * Validated proposal, PDF evidence and explicitly synthetic comparable missions.
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RfpResponse {

    private String requestId;
    private Map<String, Object> requirements;
    private Map<String, Object> proposal;
    private List<Map<String, Object>> sources;
    private List<Map<String, Object>> coverageReport;
    private List<Map<String, Object>> citations;
    private List<Map<String, Object>> similarMissions;
    private boolean evidenceValidationPassed;
    private Map<String, Object> quality;
    private String diagnostic;
}
