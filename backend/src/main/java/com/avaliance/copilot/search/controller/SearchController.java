package com.avaliance.copilot.search.controller;

import com.avaliance.copilot.search.dto.*;
import com.avaliance.copilot.search.service.SearchService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

/**
 * REST controller for search and similar missions endpoints.
 */
@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class SearchController {

    private final SearchService searchService;

    /**
     * POST /api/search — hybrid search + sourced answer.
     * Proxies to FastAPI /retrieve + /generate.
     */
    @PostMapping("/search")
    public ResponseEntity<SearchResponse> search(@Valid @RequestBody SearchRequest request) {
        SearchResponse response = searchService.search(request);
        return ResponseEntity.ok(response);
    }

    /**
     * POST /api/search/stream — streaming search via SSE.
     * Proxies to FastAPI /retrieve + /generate/stream.
     * Tokens are sent as SSE events in real-time.
     */
    @PostMapping(value = "/search/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<Flux<ServerSentEvent<String>>> searchStream(@Valid @RequestBody SearchRequest request) {
        return ResponseEntity.ok()
                .header(HttpHeaders.CACHE_CONTROL, "no-cache, no-transform")
                .header("X-Accel-Buffering", "no")
                .cacheControl(CacheControl.noCache())
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .body(searchService.searchStream(request));
    }

    /**
     * POST /api/similar — find similar missions.
     * Proxies to FastAPI /similar.
     */
    @PostMapping("/similar")
    public ResponseEntity<SimilarResponse> similar(@Valid @RequestBody SimilarRequest request) {
        SimilarResponse response = searchService.findSimilar(request);
        return ResponseEntity.ok(response);
    }
}
