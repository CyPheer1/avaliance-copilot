package com.avaliance.copilot.rfp.service;

import com.avaliance.copilot.audit.service.AuditService;
import com.avaliance.copilot.config.enums.AuditAction;
import com.avaliance.copilot.rfp.dto.RfpRequest;
import com.avaliance.copilot.rfp.dto.RfpResponse;
import com.avaliance.copilot.search.service.IaClientService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.*;

/**
 * Orchestration service for RFP structure generation.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class RfpService {

    private final IaClientService iaClientService;
    private final AuditService auditService;

    @SuppressWarnings("unchecked")
    public RfpResponse generate(RfpRequest request) {
        long startTime = System.currentTimeMillis();
        String status = "SUCCESS";
        try {
            // The RFP route is isolated from /api/search. FastAPI retrieves PDF
            // evidence first, validates physical-page citations, then optionally
            // discovers synthetic comparable missions as a separate labelled source.
            String requestId = UUID.randomUUID().toString();
            Map<String, Object> rfpRequest = new LinkedHashMap<>();
            rfpRequest.put("request_id", requestId);
            rfpRequest.put("description", request.getDescription());
            if (request.getSector() != null) rfpRequest.put("sector", request.getSector());
            if (request.getMissionType() != null) rfpRequest.put("mission_type", request.getMissionType());
            if (request.getTopK() != null) rfpRequest.put("top_k", request.getTopK());
            log.info("RFP request received requestId={} descriptionLength={} sector={} missionType={}",
                    requestId, request.getDescription().length(), request.getSector(), request.getMissionType());

            Map<String, Object> rfpResponse = iaClientService.rfp(rfpRequest);
            return RfpResponse.builder()
                    .requestId((String) rfpResponse.getOrDefault("request_id", requestId))
                    .requirements((Map<String, Object>) rfpResponse.getOrDefault("requirements", Map.of()))
                    .proposal((Map<String, Object>) rfpResponse.getOrDefault("proposal", Map.of()))
                    .sources((List<Map<String, Object>>) rfpResponse.getOrDefault("sources", List.of()))
                    .coverageReport((List<Map<String, Object>>) rfpResponse.getOrDefault("coverage_report", List.of()))
                    .citations((List<Map<String, Object>>) rfpResponse.getOrDefault("citations", List.of()))
                    .similarMissions((List<Map<String, Object>>) rfpResponse.getOrDefault("similar_missions", List.of()))
                    .evidenceValidationPassed(Boolean.TRUE.equals(rfpResponse.get("evidence_validation_passed")))
                    .quality((Map<String, Object>) rfpResponse.get("quality"))
                    .diagnostic((String) rfpResponse.get("diagnostic"))
                    .build();

        } catch (Exception e) {
            status = "ERROR";
            throw e;
        } finally {
            long duration = System.currentTimeMillis() - startTime;
            auditService.log(AuditAction.GENERATE_RFP, request.getDescription(), status, duration);
        }
    }
}
