package com.avaliance.copilot.rfp;

import com.avaliance.copilot.auth.filter.JwtAuthenticationFilter;
import com.avaliance.copilot.config.GlobalExceptionHandler;
import com.avaliance.copilot.config.IaValidationException;
import com.avaliance.copilot.rfp.controller.RfpController;
import com.avaliance.copilot.rfp.dto.RfpResponse;
import com.avaliance.copilot.rfp.service.RfpService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers;
import org.springframework.test.web.reactive.server.WebTestClient;

import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

@WebFluxTest(RfpController.class)
@Import(GlobalExceptionHandler.class)
class RfpControllerTest {

    @Autowired
    private WebTestClient webTestClient;

    @MockBean
    private RfpService rfpService;

    @MockBean
    private JwtAuthenticationFilter jwtAuthenticationFilter;

    @Test
    @DisplayName("POST /api/rfp/generate returns 422 Unprocessable Entity when brief is rejected by IA service")
    void generateRfpReturns422WhenBriefIsRejected() {
        when(rfpService.generate(any()))
                .thenThrow(new IaValidationException("Le brief fourni ne contient aucun besoin exploitable pour construire une proposition."));

        webTestClient
                .mutateWith(SecurityMockServerConfigurers.mockUser("tester").roles("ADMIN"))
                .mutateWith(SecurityMockServerConfigurers.csrf())
                .post()
                .uri("/api/rfp/generate")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "description": "Bonjour !"
                        }
                        """)
                .exchange()
                .expectStatus().isEqualTo(422)
                .expectBody()
                .jsonPath("$.status").isEqualTo(422)
                .jsonPath("$.error").isEqualTo("Unprocessable Entity")
                .jsonPath("$.message").isEqualTo("Le brief fourni ne contient aucun besoin exploitable pour construire une proposition.");
    }

    @Test
    @DisplayName("POST /api/rfp/generate returns 200 OK with 19 sections on valid brief")
    void generateRfpReturns200OnValidBrief() {
        RfpResponse response = new RfpResponse();
        response.setRequestId("test-id");
        response.setProposal(Map.of("title", "Proposition de test"));
        response.setEvidenceValidationPassed(true);

        when(rfpService.generate(any())).thenReturn(response);

        webTestClient
                .mutateWith(SecurityMockServerConfigurers.mockUser("tester").roles("ADMIN"))
                .mutateWith(SecurityMockServerConfigurers.csrf())
                .post()
                .uri("/api/rfp/generate")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "description": "Groupe hospitalier : déployer un portail patient sécurisé HDS.",
                          "sector": "sante"
                        }
                        """)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.requestId").isEqualTo("test-id")
                .jsonPath("$.proposal.title").isEqualTo("Proposition de test");
    }
}
