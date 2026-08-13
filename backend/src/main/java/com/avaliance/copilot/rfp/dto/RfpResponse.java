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

    private Map<String, Object> requirements;
    private Map<String, Object> proposal;
    /** Structured proposal content consumed directly by the presentation layer. */
    private List<Map<String, Object>> sections;
    /** Verbatim PDF excerpts, each linked to its physical source. */
    private List<Map<String, Object>> evidence;
    /** Plain-text fallback for export clients that cannot render blocks. */
    private String rfpStructure;
    private List<Map<String, Object>> citations;
    private List<Map<String, Object>> similarMissions;
    private boolean evidenceValidationPassed;
    private String diagnostic;
}
