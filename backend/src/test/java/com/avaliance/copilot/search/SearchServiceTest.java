package com.avaliance.copilot.search;

import com.avaliance.copilot.audit.service.AuditService;
import com.avaliance.copilot.config.enums.AuditAction;
import com.avaliance.copilot.search.dto.SearchRequest;
import com.avaliance.copilot.search.dto.SearchResponse;
import com.avaliance.copilot.search.dto.SimilarRequest;
import com.avaliance.copilot.search.dto.SimilarResponse;
import com.avaliance.copilot.search.service.IaClientService;
import com.avaliance.copilot.search.service.SearchService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

/**
 * Unit tests for SearchService — mocks FastAPI client (IaClientService).
 */
@ExtendWith(MockitoExtension.class)
class SearchServiceTest {

    @Mock
    private IaClientService iaClientService;

    @Mock
    private AuditService auditService;

    @InjectMocks
    private SearchService searchService;

    @Test
    @DisplayName("search() chains /retrieve → /generate and returns sourced answer")
    void search_chainsRetrieveAndGenerate() {
        Map<String, Object> retrieveResponse = Map.of(
                "chunks", List.of(
                        Map.of("chunk_id", 1, "content", "Chunk content 1", "score", 0.95),
                        Map.of("chunk_id", 2, "content", "Chunk content 2", "score", 0.87)
                )
        );
        when(iaClientService.retrieve(any())).thenReturn(retrieveResponse);

        Map<String, Object> generateResponse = Map.of(
                "answer", "La migration cloud a été réalisée avec Azure [1].",
                "confidence", 0.91,
                "citations", List.of(
                        Map.of("citation_id", "req-1:1", "request_id", "req-1", "chunk_id", 1, "mission_id", 10, "mission_title", "Migration Cloud Banque",
                                "corpus_scope", "MISSION", "content", "Chunk content 1", "score", 0.95),
                        Map.of("citation_id", "req-1:2", "request_id", "req-1", "chunk_id", 2, "document_id", 42, "document_name", "architecture.pdf",
                                "page", 7, "corpus_scope", "PDF", "content", "Chunk content 2", "score", 0.87)
                )
        );
        when(iaClientService.generate(any())).thenReturn(generateResponse);

        SearchRequest request = new SearchRequest();
        request.setQuery("migration cloud banque");
        request.setSector("banque");

        SearchResponse response = searchService.search(request);

        assertThat(response.getAnswer()).contains("migration cloud");
        assertThat(response.getConfidence()).isEqualTo(0.91);
        assertThat(response.getCitations()).hasSize(2);
        assertThat(response.getCitations().get(0).getMissionTitle()).isEqualTo("Migration Cloud Banque");
        assertThat(response.getCitations().get(0).getCitationId()).isEqualTo("req-1:1");
        assertThat(response.getCitations().get(1).getRequestId()).isEqualTo("req-1");
        assertThat(response.getCitations().get(1).getMissionId()).isNull();
        assertThat(response.getCitations().get(1).getDocumentId()).isEqualTo(42L);
        assertThat(response.getCitations().get(1).getDocumentName()).isEqualTo("architecture.pdf");
        assertThat(response.getCitations().get(1).getCorpusScope()).isEqualTo("PDF");
        assertThat(response.getCitations().get(1).getPage()).isEqualTo(7);

        verify(iaClientService).retrieve(any());
        verify(iaClientService).generate(any());
        verify(auditService).log(eq(AuditAction.SEARCH), eq("migration cloud banque"), eq("SUCCESS"), anyLong());
    }

    @Test
    @DisplayName("search() passes filters to FastAPI retrieve")
    void search_passesFilters() {
        when(iaClientService.retrieve(any())).thenReturn(Map.of("chunks", List.of()));
        when(iaClientService.generate(any())).thenReturn(Map.of(
                "answer", "Information insuffisante.",
                "confidence", 0.0
        ));

        SearchRequest request = new SearchRequest();
        request.setQuery("cybersécurité");
        request.setSector("assurance");
        request.setMissionType("cybersécurité");
        request.setYear(2024);
        request.setTopK(5);

        searchService.search(request);

        verify(iaClientService).retrieve(argThat(map -> {
            @SuppressWarnings("unchecked")
            Map<String, Object> m = (Map<String, Object>) map;
            return "cybersécurité".equals(m.get("query"))
                    && "assurance".equals(m.get("sector"))
                    && "cybersécurité".equals(m.get("mission_type"))
                    && Integer.valueOf(2024).equals(m.get("year"))
                    && Integer.valueOf(5).equals(m.get("top_k"))
                    && "PDF".equals(m.get("corpus_scope"))
                    && m.get("request_id") != null;
        }));
    }

    @Test
    @DisplayName("searchStream() emits typed status and error events")
    void searchStream_emitsTypedStatusAndErrorEvents() {
        when(iaClientService.retrieve(any())).thenReturn(Map.of("chunks", List.of()));
        when(iaClientService.generateStream(any(), any())).thenReturn(Flux.error(new IllegalStateException("stream failed")));

        SearchRequest request = new SearchRequest();
        request.setQuery("question streaming");

        var events = searchService.searchStream(request)
                .collectList()
                .block();

        assertThat(events).isNotNull();
        assertThat(events).extracting(event -> event.event()).contains("status", "error");
        assertThat(events.get(0).data()).contains("\"status\":\"retrieving\"");
        assertThat(events.get(1).data()).contains("\"status\":\"generating\"");
        assertThat(events.get(events.size() - 1).data())
                .contains("\"error\":\"stream failed\"")
                .doesNotContain("\"done\":true");
        assertThat(events).extracting(event -> event.event()).doesNotContain("done");
        verify(auditService, times(1)).log(
                eq(AuditAction.SEARCH),
                eq("question streaming"),
                eq("ERROR"),
                anyLong()
        );
    }

    @Test
    @DisplayName("searchStream() preserves FastAPI citation metadata through the terminal done event")
    void searchStream_preservesFastApiCitationMetadata() {
        when(iaClientService.retrieve(any())).thenReturn(Map.of("chunks", List.of()));
        String citations = """
                [{"citationId":"req-1:11","requestId":"req-1","chunkId":11,
                "documentId":42,"documentName":"architecture.pdf","page":7,
                "content":"Chunk content 1","score":0.95,"sourceIndex":1}]
                """.replaceAll("\\s+", "");
        when(iaClientService.generateStream(any(), any())).thenReturn(Flux.just(
                org.springframework.http.codec.ServerSentEvent.builder("{\"token\":\"Azure [1]\"}")
                        .event("delta")
                        .build(),
                org.springframework.http.codec.ServerSentEvent.builder("{\"passed\":true}")
                        .event("validation")
                        .build(),
                org.springframework.http.codec.ServerSentEvent.builder("{\"citations\":" + citations + "}")
                        .event("citation")
                        .build(),
                org.springframework.http.codec.ServerSentEvent.builder("{\"done\":true,\"citations\":" + citations + ",\"validationPassed\":true}")
                        .event("done")
                        .build()
        ));

        SearchRequest request = new SearchRequest();
        request.setQuery("question streaming");

        var events = searchService.searchStream(request).collectList().block();

        assertThat(events).isNotNull();
        assertThat(events).extracting(event -> event.event())
                .containsSubsequence("status", "status", "delta", "validation", "citation", "done");
        var citationEvent = events.stream().filter(event -> "citation".equals(event.event())).findFirst().orElseThrow();
        var doneEvent = events.stream().filter(event -> "done".equals(event.event())).findFirst().orElseThrow();
        assertThat(citationEvent.data()).contains("architecture.pdf", "\"page\":7", "\"chunkId\":11", "\"sourceIndex\":1");
        assertThat(doneEvent.data()).contains("architecture.pdf", "\"page\":7", "\"chunkId\":11", "\"sourceIndex\":1");
    }

    @Test
    @DisplayName("findSimilar() calls /similar and returns missions")
    void findSimilar_returnsMissions() {
        Map<String, Object> iaResponse = Map.of(
                "missions", List.of(
                        Map.of("id", 1, "title", "Mission A", "sector", "banque",
                                "mission_type", "modernisation", "technologies", List.of("Java", "Spring"),
                                "year", 2023, "summary", "Modernisation du SI", "similarity_score", 0.89),
                        Map.of("id", 2, "title", "Mission B", "sector", "banque",
                                "mission_type", "migration cloud", "technologies", List.of("Azure", "Kubernetes"),
                                "year", 2024, "summary", "Migration vers Azure", "similarity_score", 0.76)
                )
        );
        when(iaClientService.similar(any())).thenReturn(iaResponse);

        SimilarRequest request = new SimilarRequest();
        request.setDescription("modernisation bancaire");

        SimilarResponse response = searchService.findSimilar(request);

        assertThat(response.getMissions()).hasSize(2);
        assertThat(response.getMissions().get(0).getTitle()).isEqualTo("Mission A");
        assertThat(response.getMissions().get(0).getSimilarityScore()).isEqualTo(0.89);
        assertThat(response.getMissions().get(1).getTechnologies()).contains("Azure", "Kubernetes");

        verify(auditService).log(eq(AuditAction.SIMILAR), eq("modernisation bancaire"), eq("SUCCESS"), anyLong());
    }
}
