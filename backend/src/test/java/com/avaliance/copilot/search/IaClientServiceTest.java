package com.avaliance.copilot.search;

import com.avaliance.copilot.config.IaServiceException;
import com.avaliance.copilot.config.IaServiceProperties;
import com.avaliance.copilot.config.IaServiceUnavailableException;
import com.avaliance.copilot.config.RestClientConfig;
import com.avaliance.copilot.search.service.IaClientService;
import com.avaliance.copilot.search.service.IaStubService;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;

class IaClientServiceTest {

    private static final String INTERNAL_TOKEN = "test-internal-token";

    private HttpServer server;
    private final AtomicReference<String> requestPath = new AtomicReference<>();
    private final AtomicReference<String> requestToken = new AtomicReference<>();

    @BeforeEach
    void setUp() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.start();
    }

    @AfterEach
    void tearDown() {
        server.stop(0);
    }

    @Test
    void healthUsesExpectedPathAndInternalToken() {
        server.createContext("/health", exchange -> respond(exchange, 200, "{\"status\":\"ok\"}"));

        Map<String, Object> response = client(1000).health();

        assertThat(response).containsEntry("status", "ok");
        assertThat(requestPath.get()).isEqualTo("/health");
        assertThat(requestToken.get()).isEqualTo(INTERNAL_TOKEN);
    }

    @Test
    void healthMapsNonSuccessfulResponse() {
        server.createContext("/health", exchange -> respond(exchange, 403, "{\"detail\":\"forbidden\"}"));

        assertThatThrownBy(() -> client(1000).health()).isInstanceOf(IaServiceException.class);
    }

    @Test
    void healthMapsReadTimeoutToUnavailable() {
        server.createContext("/health", exchange -> {
            try {
                Thread.sleep(250);
                respond(exchange, 200, "{\"status\":\"ok\"}");
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
            }
        });

        assertThatThrownBy(() -> client(25).health()).isInstanceOf(IaServiceUnavailableException.class);
    }

    @Test
    void generateProposalMaps422ToIaValidationException() {
        server.createContext("/rfp", exchange -> respond(exchange, 422, "{\"detail\":\"Le brief fourni ne contient aucun besoin exploitable pour construire une proposition.\"}"));

        assertThatThrownBy(() -> client(1000).rfp(Map.of("description", "Bonjour !")))
                .isInstanceOf(com.avaliance.copilot.config.IaValidationException.class)
                .hasMessage("Le brief fourni ne contient aucun besoin exploitable pour construire une proposition.");
    }

    private IaClientService client(int readTimeoutMs) {
        IaServiceProperties properties = new IaServiceProperties();
        properties.setBaseUrl("http://127.0.0.1:" + server.getAddress().getPort());
        properties.setInternalToken(INTERNAL_TOKEN);
        properties.setConnectTimeoutMs(1000);
        properties.setReadTimeoutMs(readTimeoutMs);
        properties.setStubEnabled(false);
        RestClientConfig config = new RestClientConfig();
        return new IaClientService(
                config.iaRestClient(properties),
                config.iaWebClient(properties),
                properties,
                mock(IaStubService.class)
        );
    }

    private void respond(HttpExchange exchange, int status, String body) throws IOException {
        requestPath.set(exchange.getRequestURI().getPath());
        requestToken.set(exchange.getRequestHeaders().getFirst("X-Internal-Token"));
        byte[] payload = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, payload.length);
        exchange.getResponseBody().write(payload);
        exchange.close();
    }
}