package com.avaliance.copilot.rfp.controller;

import com.avaliance.copilot.rfp.dto.RfpRequest;
import com.avaliance.copilot.rfp.dto.RfpResponse;
import com.avaliance.copilot.rfp.service.RfpService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

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
        RfpResponse response = rfpService.generate(request);
        return ResponseEntity.ok(response);
    }
}
