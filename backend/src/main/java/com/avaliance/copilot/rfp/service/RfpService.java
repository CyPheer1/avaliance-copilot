package com.avaliance.copilot.rfp.service;

import com.avaliance.copilot.audit.service.AuditService;
import com.avaliance.copilot.auth.entity.AppUser;
import com.avaliance.copilot.auth.repository.AppUserRepository;
import com.avaliance.copilot.config.enums.AuditAction;
import com.avaliance.copilot.rfp.dto.RfpJobAcceptedResponse;
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
    private final AppUserRepository appUserRepository;

    private AppUser owner(String username) {
        return appUserRepository.findByUsername(username)
                .orElseThrow(() -> new IllegalArgumentException("Authenticated user was not found"));
    }

    @SuppressWarnings("unchecked")
    public RfpResponse generate(RfpRequest request) {
        long startTime = System.currentTimeMillis();
        String status = "SUCCESS";
        try {
            // The RFP route is isolated from /api/search. FastAPI retrieves PDF
            // evidence first, validates physical-page citations, then optionally
            // discovers synthetic comparable missions as a separate labelled source.
            String requestId = org.slf4j.MDC.get(com.avaliance.copilot.config.RequestIdFilter.REQUEST_ID_MDC_KEY);
            if (requestId == null || requestId.isBlank()) {
                requestId = UUID.randomUUID().toString();
                org.slf4j.MDC.put(com.avaliance.copilot.config.RequestIdFilter.REQUEST_ID_MDC_KEY, requestId);
            }
            Map<String, Object> rfpRequest = new LinkedHashMap<>();
            rfpRequest.put("request_id", requestId);
            rfpRequest.put("mode", request.getMode() != null ? request.getMode() : "standard");
            rfpRequest.put("description", request.getDescription());
            if (request.getSector() != null) rfpRequest.put("sector", request.getSector());
            if (request.getMissionType() != null) rfpRequest.put("mission_type", request.getMissionType());
            if (request.getTopK() != null) rfpRequest.put("top_k", request.getTopK());
            log.info("RFP request received requestId={} descriptionLength={} sector={} missionType={}",
                    requestId, request.getDescription() != null ? request.getDescription().length() : 0, request.getSector(), request.getMissionType());

            Map<String, Object> rfpResponse = iaClientService.rfp(rfpRequest);
            return RfpResponse.builder()
                    .jobId((String) rfpResponse.get("job_id"))
                    .requestId((String) rfpResponse.getOrDefault("request_id", requestId))
                    .mode((String) rfpResponse.getOrDefault("mode", request.getMode() != null ? request.getMode() : "standard"))
                    .status((String) rfpResponse.getOrDefault("status", "completed"))
                    .requirements((Map<String, Object>) rfpResponse.getOrDefault("requirements", Map.of()))
                    .proposal((Map<String, Object>) rfpResponse.getOrDefault("proposal", Map.of()))
                    .annexes((Map<String, Object>) rfpResponse.getOrDefault("annexes", Map.of()))
                    .metrics((Map<String, Object>) rfpResponse.getOrDefault("metrics", Map.of()))
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
            String safeAuditQuery = "sector=" + request.getSector() + ", length=" + (request.getDescription() != null ? request.getDescription().length() : 0);
            auditService.log(AuditAction.GENERATE_RFP, safeAuditQuery, status, duration);
        }
    }

    public RfpJobAcceptedResponse createFullJob(RfpRequest request, String username) {
        if (!"full".equals(request.getMode())) {
            throw new IllegalArgumentException("Only full mode may be submitted as an asynchronous RFP job");
        }
        AppUser owner = owner(username);
        String requestId = org.slf4j.MDC.get(com.avaliance.copilot.config.RequestIdFilter.REQUEST_ID_MDC_KEY);
        if (requestId == null || requestId.isBlank()) {
            requestId = UUID.randomUUID().toString();
            org.slf4j.MDC.put(com.avaliance.copilot.config.RequestIdFilter.REQUEST_ID_MDC_KEY, requestId);
        }
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("request_id", requestId);
        payload.put("mode", "full");
        payload.put("description", request.getDescription());
        if (request.getSector() != null) payload.put("sector", request.getSector());
        Map<String, Object> accepted = iaClientService.createRfpJob(payload, owner.getId(), owner.getRole());
        return RfpJobAcceptedResponse.builder().jobId((String) accepted.get("job_id"))
                .status((String) accepted.getOrDefault("status", "queued"))
                .requestId((String) accepted.getOrDefault("request_id", requestId)).build();
    }

    public Map<String, Object> getJob(UUID jobId, String username) {
        AppUser owner = owner(username);
        return iaClientService.getRfpJob(jobId, owner.getId(), owner.getRole());
    }

    public Map<String, Object> getJobResult(UUID jobId, String username) {
        AppUser owner = owner(username);
        return iaClientService.getRfpJobResult(jobId, owner.getId(), owner.getRole());
    }

    public Map<String, Object> cancelJob(UUID jobId, String username) {
        AppUser owner = owner(username);
        return iaClientService.cancelRfpJob(jobId, owner.getId(), owner.getRole());
    }
}
