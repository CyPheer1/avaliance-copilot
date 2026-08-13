package com.avaliance.copilot.search;

import com.avaliance.copilot.auth.filter.JwtAuthenticationFilter;
import com.avaliance.copilot.search.controller.SearchController;
import com.avaliance.copilot.search.dto.SearchResponse;
import com.avaliance.copilot.search.service.SearchService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers;
import org.springframework.test.web.reactive.server.WebTestClient;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(SearchController.class)
class SearchControllerTest {

    @Autowired
    private WebTestClient webTestClient;

    @MockBean
    private SearchService searchService;

    @MockBean
    private JwtAuthenticationFilter jwtAuthenticationFilter;

    @Test
    @DisplayName("/api/search rejects eval-only mixed scope")
    void searchRejectsEvalOnlyMixedScope() {
        webTestClient
                .mutateWith(SecurityMockServerConfigurers.mockUser("tester").roles("ADMIN"))
                .mutateWith(SecurityMockServerConfigurers.csrf())
                .post()
                .uri("/api/search")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "query": "Qui a pris en charge la partie flux temps réel ?",
                          "corpusScope": "mixed_pdf_mission_eval_only"
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    @DisplayName("/api/search accepts normal PDF production requests")
    void searchAcceptsNormalProductionRequest() {
        SearchResponse response = new SearchResponse();
        response.setAnswer("Pauline Vasseur — Ingénierie data — flux temps réel [1]");
        response.setConfidence(0.91);
        response.setCitations(List.of());
        when(searchService.search(any())).thenReturn(response);

        webTestClient
                .mutateWith(SecurityMockServerConfigurers.mockUser("tester").roles("ADMIN"))
                .mutateWith(SecurityMockServerConfigurers.csrf())
                .post()
                .uri("/api/search")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "query": "Qui a pris en charge la partie flux temps réel ?",
                          "corpusScope": "PDF"
                        }
                        """)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.answer").isEqualTo("Pauline Vasseur — Ingénierie data — flux temps réel [1]")
                .jsonPath("$.confidence").isEqualTo(0.91);

        verify(searchService).search(any());
    }
}
