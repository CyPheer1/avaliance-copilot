package com.avaliance.copilot.config;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.client.RestClient;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

import java.net.http.HttpClient.Builder;
import java.time.Duration;

/**
 * Configures the HTTP clients used for internal communication with the IA service (FastAPI).
 */
@Configuration
public class RestClientConfig {

    @Bean
    public RestClient iaRestClient(IaServiceProperties properties) {
        Builder httpClientBuilder = java.net.http.HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(properties.getConnectTimeoutMs()));

        JdkClientHttpRequestFactory requestFactory = new JdkClientHttpRequestFactory(httpClientBuilder.build());
        requestFactory.setReadTimeout(Duration.ofMillis(properties.getReadTimeoutMs()));

        return RestClient.builder()
                .requestFactory(requestFactory)
                .baseUrl(properties.getBaseUrl())
                .defaultHeader("X-Internal-Token", properties.getInternalToken())
                .build();
    }

    @Bean
    public WebClient iaWebClient(IaServiceProperties properties) {
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, properties.getConnectTimeoutMs())
                .responseTimeout(Duration.ofMillis(properties.getReadTimeoutMs()));

        return WebClient.builder()
                .baseUrl(properties.getBaseUrl())
                .defaultHeader("X-Internal-Token", properties.getInternalToken())
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
