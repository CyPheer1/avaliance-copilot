package com.avaliance.copilot.config;

import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.annotation.Validated;

/**
 * Configuration for the internal IA service (FastAPI).
 */
@Getter
@Setter
@Validated
@Configuration
@ConfigurationProperties(prefix = "app.ia-service")
public class IaServiceProperties {

    @NotBlank(message = "IA_SERVICE_URL must be provided")
    private String baseUrl;

    @NotBlank(message = "INTERNAL_TOKEN must be provided for IA service authentication")
    private String internalToken;

    private int connectTimeoutMs = 5000;
    private int readTimeoutMs = 120000; // default 2 minutes for LLM generation
    private boolean stubEnabled = false;
}
