package com.avaliance.copilot.integration;

import com.avaliance.copilot.audit.entity.AuditLog;
import com.avaliance.copilot.audit.repository.AuditLogRepository;
import com.avaliance.copilot.auth.dto.LoginRequest;
import com.avaliance.copilot.config.IaServiceException;
import com.avaliance.copilot.config.enums.AuditAction;
import com.avaliance.copilot.rfp.dto.RfpRequest;
import com.avaliance.copilot.search.dto.SearchRequest;
import com.avaliance.copilot.search.service.IaClientService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Validates that audit logs are correctly recorded for business requests,
 * both on success and failure (e.g. missing required fields), 
 * capturing status and duration.
 */
@AutoConfigureMockMvc
class AuditIT extends AbstractIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private AuditLogRepository auditLogRepository;

    @MockBean
    private IaClientService iaClientService;

    private String adminToken;

    @BeforeEach
    void setUp() throws Exception {
        auditLogRepository.deleteAll();

        // Login to get a valid token
        LoginRequest login = new LoginRequest("admin", "admin123");
        String response = mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(login)))
                .andReturn().getResponse().getContentAsString();
                
        adminToken = objectMapper.readTree(response).get("token").asText();
    }

    @Test
    @DisplayName("Successful search request records an audit log with SUCCESS status")
    void successfulSearchRecordsAudit() throws Exception {
        SearchRequest request = new SearchRequest();
        request.setQuery("cloud migration");

        mockMvc.perform(post("/api/search")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk());

        List<AuditLog> logs = auditLogRepository.findAll();
        assertThat(logs).hasSize(1);
        AuditLog logEntry = logs.get(0);
        
        assertThat(logEntry.getAction()).isEqualTo(AuditAction.SEARCH.name());
        assertThat(logEntry.getQueryText()).isEqualTo("cloud migration");
        assertThat(logEntry.getStatus()).isEqualTo("SUCCESS");
        assertThat(logEntry.getDurationMs()).isNotNull().isGreaterThanOrEqualTo(0L);
        assertThat(logEntry.getUserId()).isNotNull();
    }

    @Test
    @DisplayName("IA failure records an audit log with ERROR status")
    void failedRfpRecordsAuditWithErrorStatus() throws Exception {
        RfpRequest request = new RfpRequest("Migration cloud critique", "standard", "Banque", "Conseil", 5);
        when(iaClientService.similar(anyMap())).thenThrow(new IaServiceException("IA unavailable"));

        mockMvc.perform(post("/api/rfp/generate")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadGateway());

        List<AuditLog> logs = auditLogRepository.findAll();
        assertThat(logs).hasSize(1);
        AuditLog logEntry = logs.get(0);
        assertThat(logEntry.getAction()).isEqualTo(AuditAction.GENERATE_RFP.name());
        assertThat(logEntry.getQueryText()).isEqualTo("Migration cloud critique");
        assertThat(logEntry.getStatus()).isEqualTo("ERROR");
        assertThat(logEntry.getDurationMs()).isNotNull().isGreaterThanOrEqualTo(0L);
        assertThat(logEntry.getUserId()).isNotNull();
    }
}
