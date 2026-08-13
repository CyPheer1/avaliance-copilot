package com.avaliance.copilot.search.service;

import com.avaliance.copilot.audit.service.AuditService;
import com.avaliance.copilot.config.enums.AuditAction;
import com.avaliance.copilot.search.dto.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Orchestration service for search and similar missions.
 * Chains calls to FastAPI (/retrieve → /generate) and logs audit entries.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class SearchService {

    private final IaClientService iaClientService;
    private final AuditService auditService;

    @SuppressWarnings("unchecked")
    public SearchResponse search(SearchRequest request) {
        long startTime = System.currentTimeMillis();
        String status = "SUCCESS";
        try {
            String requestId = resolveRequestId(request);
            Map<String, Object> retrieveRequest = buildRetrieveRequest(request, requestId);
            Map<String, Object> retrieveResponse = iaClientService.retrieve(retrieveRequest);

            Map<String, Object> generateRequest = new LinkedHashMap<>();
            generateRequest.put("query", request.getQuery());
            generateRequest.put("request_id", requestId);
            generateRequest.put("chunks", retrieveResponse.get("chunks"));

            Map<String, Object> generateResponse = iaClientService.generate(generateRequest);

            SearchResponse response = new SearchResponse();
            response.setAnswer((String) generateResponse.get("answer"));
            response.setConfidence((Double) generateResponse.get("confidence"));

            List<SearchResponse.Citation> citations = new ArrayList<>();
            List<Map<String, Object>> rawCitations = (List<Map<String, Object>>) generateResponse.get("citations");
            if (rawCitations != null) {
                for (Map<String, Object> c : rawCitations) {
                    citations.add(SearchResponse.Citation.builder()
                            .citationId((String) firstValue(c, "citation_id", "citationId"))
                            .requestId((String) firstValue(c, "request_id", "requestId"))
                            .chunkId(toLong(firstValue(c, "chunk_id", "chunkId")))
                            .missionId(toLong(firstValue(c, "mission_id", "missionId")))
                            .missionTitle((String) firstValue(c, "mission_title", "missionTitle"))
                            .documentId(toLong(firstValue(c, "document_id", "documentId")))
                            .documentName((String) firstValue(c, "document_name", "documentName"))
                            .page(toInt(c.get("page")))
                            .corpusScope((String) firstValue(c, "corpus_scope", "corpusScope"))
                            .content((String) c.get("content"))
                            .score(toDouble(c.get("score")))
                            .rrfScore(toDouble(firstValue(c, "rrf_score", "rrfScore")))
                            .relevanceScore(toDouble(firstValue(c, "relevance_score", "relevanceScore")))
                            .build());
                }
            }
            response.setCitations(citations);

            return response;

        } catch (Exception e) {
            status = "ERROR";
            throw e;
        } finally {
            long duration = System.currentTimeMillis() - startTime;
            auditService.log(AuditAction.SEARCH, request.getQuery(), status, duration);
        }
    }

    private Object firstValue(Map<String, Object> values, String primaryKey, String fallbackKey) {
        Object primaryValue = values.get(primaryKey);
        return primaryValue != null ? primaryValue : values.get(fallbackKey);
    }

    public Flux<ServerSentEvent<String>> searchStream(SearchRequest request) {
        long startMillis = System.currentTimeMillis();
        long startNanos = System.nanoTime();
        AtomicBoolean auditLogged = new AtomicBoolean(false);
        AtomicBoolean firstForwardedPayloadLogged = new AtomicBoolean(false);
        AtomicLong upstreamConnectedAtMillis = new AtomicLong(-1L);

        return Flux.defer(() -> {
            log.info("searchStream subscribed query='{}'", request.getQuery());

            Flux<ServerSentEvent<String>> retrievalStatus = Flux.just(event("status", "{\"status\":\"retrieving\"}"));

            Flux<ServerSentEvent<String>> generationPipeline = Mono.fromCallable(() -> {
                        long retrievalStart = System.currentTimeMillis();
                        String requestId = resolveRequestId(request);
                        log.info("searchStream retrieval started query='{}' requestId='{}'", request.getQuery(), requestId);
                        Map<String, Object> retrieveRequest = buildRetrieveRequest(request, requestId);
                        Map<String, Object> retrieveResponse = iaClientService.retrieve(retrieveRequest);
                        log.info(
                                "searchStream retrieval finished query='{}' in {} ms",
                                request.getQuery(),
                                System.currentTimeMillis() - retrievalStart
                        );

                        Map<String, Object> generateRequest = new LinkedHashMap<>();
                        generateRequest.put("query", request.getQuery());
                        generateRequest.put("request_id", requestId);
                        generateRequest.put("chunks", retrieveResponse.get("chunks"));
                        return generateRequest;
                    })
                    .subscribeOn(Schedulers.boundedElastic())
                    .flatMapMany(generateRequest -> Flux.concat(
                            Flux.just(event("status", "{\"status\":\"generating\"}")),
                            iaClientService.generateStream(generateRequest, () -> {
                                        long connectedAt = System.currentTimeMillis();
                                        upstreamConnectedAtMillis.compareAndSet(-1L, connectedAt);
                                        log.info(
                                                "searchStream upstream connected query='{}' after {} ms",
                                                request.getQuery(),
                                                connectedAt - startMillis
                                        );
                                    })
                                    .map(upstreamEvent -> {
                                        if (firstForwardedPayloadLogged.compareAndSet(false, true)) {
                                            long firstForwardAt = System.currentTimeMillis();
                                            log.info(
                                                    "searchStream first payload forwarded query='{}' after {} ms (upstream delta {} ms)",
                                                    request.getQuery(),
                                                    firstForwardAt - startMillis,
                                                    upstreamConnectedAtMillis.get() > 0 ? firstForwardAt - upstreamConnectedAtMillis.get() : -1
                                            );
                                        }
                                        String payload = upstreamEvent.data();
                                        String upstreamType = upstreamEvent.event();
                                        return event(
                                                upstreamType != null && !upstreamType.isBlank()
                                                        ? upstreamType
                                                        : eventTypeForPayload(payload),
                                                payload
                                        );
                                    })
                    ));

            return Flux.concat(retrievalStatus, generationPipeline);
        }).doOnCancel(() -> {
                    if (auditLogged.compareAndSet(false, true)) {
                        long duration = System.currentTimeMillis() - startMillis;
                        log.info("searchStream cancelled query='{}' after {} ms", request.getQuery(), duration);
                        auditService.log(AuditAction.SEARCH, request.getQuery(), "CANCELLED", duration);
                    }
                })
                .doOnError(error -> {
                    if (auditLogged.compareAndSet(false, true)) {
                        log.error("SSE streaming search failed query='{}': {}", request.getQuery(), error.getMessage());
                        auditService.log(AuditAction.SEARCH, request.getQuery(), "ERROR", System.currentTimeMillis() - startMillis);
                    }
                })
                .onErrorResume(error -> Flux.just(event(
                        "error",
                        "{\"error\":\""
                                + escapeJson(Optional.ofNullable(error.getMessage()).orElse("IA streaming failed"))
                                + "\"}"
                )))
                .doOnComplete(() -> {
                    if (auditLogged.compareAndSet(false, true)) {
                        long duration = System.currentTimeMillis() - startMillis;
                        log.info(
                                "searchStream completed query='{}' in {} ms ({} ms from nano clock)",
                                request.getQuery(),
                                duration,
                                (System.nanoTime() - startNanos) / 1_000_000
                        );
                        auditService.log(AuditAction.SEARCH, request.getQuery(), "SUCCESS", duration);
                    }
                });
    }

    @SuppressWarnings("unchecked")
    public SimilarResponse findSimilar(SimilarRequest request) {
        long startTime = System.currentTimeMillis();
        String status = "SUCCESS";
        try {
            Map<String, Object> iaRequest = new LinkedHashMap<>();
            iaRequest.put("description", request.getDescription());
            if (request.getSector() != null) iaRequest.put("sector", request.getSector());
            if (request.getMissionType() != null) iaRequest.put("mission_type", request.getMissionType());
            if (request.getTopK() != null) iaRequest.put("top_k", request.getTopK());

            Map<String, Object> iaResponse = iaClientService.similar(iaRequest);

            List<SimilarResponse.SimilarMission> missions = new ArrayList<>();
            List<Map<String, Object>> rawMissions = (List<Map<String, Object>>) iaResponse.get("missions");
            if (rawMissions != null) {
                for (Map<String, Object> m : rawMissions) {
                    Object techObj = m.get("technologies");
                    String[] techs = techObj instanceof List
                            ? ((List<String>) techObj).toArray(new String[0])
                            : new String[0];

                    missions.add(SimilarResponse.SimilarMission.builder()
                            .id(toLong(m.get("id")))
                            .title((String) m.get("title"))
                            .sector((String) m.get("sector"))
                            .missionType((String) m.get("mission_type"))
                            .technologies(techs)
                            .year(toInt(m.get("year")))
                            .summary((String) m.get("summary"))
                            .similarityScore(toDouble(m.get("similarity_score")))
                            .build());
                }
            }

            return SimilarResponse.builder().missions(missions).build();

        } catch (Exception e) {
            status = "ERROR";
            throw e;
        } finally {
            long duration = System.currentTimeMillis() - startTime;
            auditService.log(AuditAction.SIMILAR, request.getDescription(), status, duration);
        }
    }

    private Map<String, Object> buildRetrieveRequest(SearchRequest request, String requestId) {
        Map<String, Object> retrieveRequest = new LinkedHashMap<>();
        retrieveRequest.put("query", request.getQuery());
        retrieveRequest.put("request_id", requestId);
        retrieveRequest.put("corpus_scope", request.getCorpusScope() != null ? request.getCorpusScope() : "PDF");
        if (request.getSector() != null) retrieveRequest.put("sector", request.getSector());
        if (request.getMissionType() != null) retrieveRequest.put("mission_type", request.getMissionType());
        if (request.getYear() != null) retrieveRequest.put("year", request.getYear());
        if (request.getTopK() != null) retrieveRequest.put("top_k", request.getTopK());
        return retrieveRequest;
    }

    private String resolveRequestId(SearchRequest request) {
        return request.getRequestId() != null && !request.getRequestId().isBlank()
                ? request.getRequestId()
                : UUID.randomUUID().toString();
    }

    private ServerSentEvent<String> event(String event, String payload) {
        return ServerSentEvent.<String>builder(payload)
                .event(event)
                .build();
    }

    private String eventTypeForPayload(String payload) {
        if (payload.contains("\"error\"")) {
            return "error";
        }
        if (payload.contains("\"done\"")) {
            return "done";
        }
        if (payload.contains("\"heartbeat\"")) {
            return "heartbeat";
        }
        if (payload.contains("\"citation\"") || payload.contains("\"citations\"")) {
            return "citation";
        }
        if (payload.contains("\"evidence\"")) {
            return "evidence";
        }
        if (payload.contains("\"validationPassed\"") || payload.contains("\"passed\"")) {
            return "validation";
        }
        if (payload.contains("\"status\"")) {
            return "status";
        }
        if (payload.contains("\"token\"")) {
            return "delta";
        }
        return "message";
    }

    private String escapeJson(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private Long toLong(Object val) {
        if (val == null) return null;
        if (val instanceof Number n) return n.longValue();
        return Long.parseLong(val.toString());
    }

    private Integer toInt(Object val) {
        if (val == null) return null;
        if (val instanceof Number n) return n.intValue();
        return Integer.parseInt(val.toString());
    }

    private Double toDouble(Object val) {
        if (val == null) return null;
        if (val instanceof Number n) return n.doubleValue();
        return Double.parseDouble(val.toString());
    }
}
