package com.avaliance.copilot.search.service;

import com.avaliance.copilot.config.IaServiceException;
import com.avaliance.copilot.config.IaServiceProperties;
import com.avaliance.copilot.config.IaServiceUnavailableException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

import java.util.Map;
import java.util.Objects;

/**
 * HTTP client for calling the internal FastAPI IA service.
 * Uses RestClient for one-shot requests and WebClient for true streaming.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class IaClientService {

    private static final ParameterizedTypeReference<ServerSentEvent<String>> SSE_STRING_EVENT =
            new ParameterizedTypeReference<>() {};

    private final RestClient iaRestClient;
    private final WebClient iaWebClient;
    private final IaServiceProperties iaServiceProperties;
    private final IaStubService iaStubService;

    @SuppressWarnings("unchecked")
    public Map<String, Object> retrieve(Map<String, Object> request) {
        if (iaServiceProperties.isStubEnabled()) {
            return iaStubService.retrieve(request);
        }
        return callPost("/retrieve", request);
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> generate(Map<String, Object> request) {
        if (iaServiceProperties.isStubEnabled()) {
            return iaStubService.generate(request);
        }
        return callPost("/generate", request);
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> similar(Map<String, Object> request) {
        if (iaServiceProperties.isStubEnabled()) {
            return iaStubService.similar(request);
        }
        return callPost("/similar", request);
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> rfp(Map<String, Object> request) {
        if (iaServiceProperties.isStubEnabled()) {
            return iaStubService.rfp(request);
        }
        return callPost("/rfp", request);
    }

    public Flux<ServerSentEvent<String>> generateStream(Map<String, Object> request, Runnable onUpstreamConnected) {
        if (iaServiceProperties.isStubEnabled()) {
            onUpstreamConnected.run();
            Map<String, Object> stubResult = iaStubService.generate(request);
            String answer = (String) stubResult.getOrDefault("answer", "Réponse stub.");
            return Flux.just(
                    ServerSentEvent.builder("{\"token\": \"" + answer.replace("\"", "\\\"") + "\"}")
                            .event("delta")
                            .build(),
                    ServerSentEvent.builder("{\"done\": true, \"citations\": [], \"confidence\": 0.5}")
                            .event("done")
                            .build()
            );
        }

        log.debug("Calling IA service: POST /generate/stream (SSE)");
        return iaWebClient.post()
                .uri("/generate/stream")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .bodyValue(request)
                .exchangeToFlux(response -> {
                    if (response.statusCode().isError()) {
                        return response.bodyToMono(String.class)
                                .defaultIfEmpty("")
                                .flatMapMany(body -> Flux.error(new IaServiceException(
                                        "IA service streaming failed: HTTP " + response.statusCode().value()
                                                + (body.isBlank() ? "" : " — " + body)
                                )));
                    }
                    onUpstreamConnected.run();
                    return response.bodyToFlux(SSE_STRING_EVENT)
                            .filter(event -> Objects.nonNull(event.data()));
                })
                .onErrorMap(error -> handleException("IA service streaming call failed", error));
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> health() {
        if (iaServiceProperties.isStubEnabled()) {
            return iaStubService.health();
        }
        try {
            return iaRestClient.get()
                    .uri("/health")
                    .retrieve()
                    .body(Map.class);
        } catch (RestClientException e) {
            throw handleException("IA service health check failed", e);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> ingestDocument(
            Long documentId,
            String filename,
            String mediaType,
            byte[] content) {
        if (iaServiceProperties.isStubEnabled()) {
            throw new IaServiceUnavailableException("Document indexing requires the real IA service.");
        }
        MultiValueMap<String, Object> parts = new LinkedMultiValueMap<>();
        parts.add("document_id", documentId.toString());
        parts.add("file", new ByteArrayResource(content) {
            @Override
            public String getFilename() {
                return filename;
            }
        });
        try {
            return iaRestClient.post()
                    .uri("/documents/ingest")
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(parts)
                    .retrieve()
                    .body(Map.class);
        } catch (RestClientException exception) {
            throw handleException("IA document indexing failed", exception);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> callPost(String path, Map<String, Object> request) {
        try {
            log.debug("Calling IA service: POST {}", path);
            return iaRestClient.post()
                    .uri(path)
                    .body(request)
                    .retrieve()
                    .body(Map.class);
        } catch (RestClientException e) {
            throw handleException("IA service call failed: " + path, e);
        }
    }

    private IaServiceException handleException(String prefix, Throwable error) {
        if (error instanceof IaServiceException iaServiceException) {
            return iaServiceException;
        }
        if (error instanceof org.springframework.web.client.RestClientResponseException responseException) {
            int statusCode = responseException.getStatusCode().value();
            String responseBody = responseException.getResponseBodyAsString();
            log.error("{} — HTTP status {}: {}", prefix, statusCode, responseBody);
            if (statusCode == 422 || statusCode == 400) {
                throw new IllegalArgumentException(responseBody.isBlank() ? "Requête invalide ou brief non exploitable" : responseBody);
            }
        }
        String message = error.getMessage() != null ? error.getMessage() : error.getClass().getSimpleName();
        String lowered = message.toLowerCase();
        if (lowered.contains("timeout") || lowered.contains("timed out") || lowered.contains("connection refused")) {
            log.error("{} — Unavailable (timeout/offline): {}", prefix, message);
            return new IaServiceUnavailableException(prefix + " — " + message, error);
        }
        log.error("{} — Error: {}", prefix, message);
        return new IaServiceException(prefix + " — " + message, error);
    }
}
