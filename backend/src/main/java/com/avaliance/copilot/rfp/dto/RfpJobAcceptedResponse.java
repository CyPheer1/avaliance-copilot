package com.avaliance.copilot.rfp.dto;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class RfpJobAcceptedResponse {
    private String jobId;
    private String status;
    private String requestId;
}
