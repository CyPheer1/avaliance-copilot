package com.avaliance.copilot.rfp.controller;

import com.avaliance.copilot.rfp.dto.RfpJobAcceptedResponse;
import com.avaliance.copilot.rfp.dto.RfpRequest;
import com.avaliance.copilot.rfp.dto.RfpResponse;
import com.avaliance.copilot.rfp.service.RfpService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.UUID;

/**
 * REST controller for RFP generation.
 */
@RestController
@RequestMapping("/api/rfp")
@RequiredArgsConstructor
public class RfpController {

    private final RfpService rfpService;

    /**
     * POST /api/rfp/generate — generate a proposal structure.
     */
    @PostMapping("/generate")
    public ResponseEntity<RfpResponse> generateRfp(@Valid @RequestBody RfpRequest request) {
        if ("full".equals(request.getMode())) {
            throw new IllegalArgumentException("Full mode must use POST /api/rfp/jobs");
        }
        return ResponseEntity.ok(rfpService.generate(request));
    }

    @PostMapping("/jobs")
    public ResponseEntity<RfpJobAcceptedResponse> createJob(@Valid @RequestBody RfpRequest request, Authentication authentication) {
        return ResponseEntity.status(HttpStatus.ACCEPTED).body(rfpService.createFullJob(request, authentication.getName()));
    }

    @GetMapping("/jobs/{jobId}")
    public ResponseEntity<Map<String, Object>> getJob(@PathVariable UUID jobId, Authentication authentication) {
        return ResponseEntity.ok(rfpService.getJob(jobId, authentication.getName()));
    }

    @GetMapping("/jobs/{jobId}/result")
    public ResponseEntity<Map<String, Object>> getJobResult(@PathVariable UUID jobId, Authentication authentication) {
        return ResponseEntity.ok(rfpService.getJobResult(jobId, authentication.getName()));
    }

    @PostMapping("/jobs/{jobId}/cancel")
    public ResponseEntity<Map<String, Object>> cancelJob(@PathVariable UUID jobId, Authentication authentication) {
        return ResponseEntity.ok(rfpService.cancelJob(jobId, authentication.getName()));
    }
}
