package com.avaliance.copilot.integration;

import com.avaliance.copilot.auth.service.JwtService;
import com.avaliance.copilot.search.dto.SearchRequest;
import com.fasterxml.jackson.databind.ObjectMapper;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestPropertySource;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;


import static org.assertj.core.api.Assertions.assertThat;

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@TestPropertySource(properties = "app.ia-service.stub-enabled=false")
class SearchStreamIT extends AbstractIntegrationTest {

    private static MockWebServer upstreamServer;

    @LocalServerPort
    private int port;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private JwtService jwtService;


    @BeforeAll
    static void startUpstream() throws Exception {
        upstreamServer = new MockWebServer();
        upstreamServer.start();
    }

    @AfterAll
    static void stopUpstream() throws Exception {
        if (upstreamServer != null) {
            upstreamServer.shutdown();
        }
    }

    @BeforeEach
    void resetUpstream() throws Exception {
        RecordedRequest request;
        while ((request = upstreamServer.takeRequest(10, TimeUnit.MILLISECONDS)) != null) {
            // drain prior requests between runs
        }
    }

    @DynamicPropertySource
    static void overrideIaProperties(DynamicPropertyRegistry registry) {
        registry.add("app.ia-service.base-url", () -> upstreamServer.url("/").toString());
        registry.add("app.ia-service.internal-token", () -> "test-token");
        registry.add("app.ia-service.stub-enabled", () -> false);
    }

    @Test
    @DisplayName("/api/search/stream forwards delayed upstream chunks incrementally")
    void searchStream_forwardsDelayedChunksIncrementally() throws Exception {
        upstreamServer.enqueue(new MockResponse()
                .setHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .setBody("""
                        {"chunks":[{"chunk_id":11,"content":"chunk one","score":0.99}]}
                        """));

        upstreamServer.enqueue(new MockResponse()
                .setHeader(HttpHeaders.CONTENT_TYPE, MediaType.TEXT_EVENT_STREAM_VALUE)
                .setChunkedBody("""
                        event: delta
                        data: {"token":"alpha"}
                        
                        event: delta
                        data: {"token":"beta"}
                        
                        event: done
                        data: {"done":true,"citations":[],"confidence":0.9}
                        
                        """, 24)
                .throttleBody(24, 350, TimeUnit.MILLISECONDS));

        SearchRequest requestBody = new SearchRequest();
        requestBody.setQuery("test streaming query");
        String token = jwtService.generateToken("admin", "ADMIN");

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + "/api/search/stream"))
                .timeout(Duration.ofSeconds(20))
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                .header(HttpHeaders.ACCEPT, MediaType.TEXT_EVENT_STREAM_VALUE)
                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(requestBody)))
                .build();

        long startedAt = System.nanoTime();
        HttpResponse<InputStream> response = client.send(request, HttpResponse.BodyHandlers.ofInputStream());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().firstValue(HttpHeaders.CACHE_CONTROL)).hasValueSatisfying(value -> assertThat(value).contains("no-cache"));
        assertThat(response.headers().firstValue("X-Accel-Buffering")).contains("no");

        List<Long> deltaTimesMs = new ArrayList<>();
        StringBuilder body = new StringBuilder();
        String currentEvent = null;

        try (InputStream inputStream = response.body();
             BufferedReader reader = new BufferedReader(new InputStreamReader(inputStream, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                body.append(line).append('\n');
                if (line.startsWith("event:")) {
                    currentEvent = line.substring("event:".length()).trim();
                    continue;
                }
                if (line.isBlank()) {
                    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - startedAt);
                    if ("delta".equals(currentEvent)) {
                        deltaTimesMs.add(elapsedMs);
                    }
                    if ("done".equals(currentEvent)) {
                        break;
                    }
                    currentEvent = null;
                }
            }
        }

        RecordedRequest retrieveRequest = upstreamServer.takeRequest(1, TimeUnit.SECONDS);
        RecordedRequest generateRequest = upstreamServer.takeRequest(1, TimeUnit.SECONDS);

        assertThat(retrieveRequest).isNotNull();
        assertThat(generateRequest).isNotNull();
        assertThat(retrieveRequest.getPath()).isEqualTo("/retrieve");
        assertThat(generateRequest.getPath()).isEqualTo("/generate/stream");
        assertThat(deltaTimesMs).hasSizeGreaterThanOrEqualTo(2);
        assertThat(deltaTimesMs.get(1) - deltaTimesMs.get(0)).isGreaterThanOrEqualTo(200L);
        assertThat(body.toString()).contains("event:status");
        assertThat(body.toString()).contains("event:delta");
        assertThat(body.toString()).contains("alpha");
        assertThat(body.toString()).contains("beta");
        assertThat(body.toString()).contains("event:done");
    }
}
