package com.avaliance.copilot.config;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.annotation.Validated;

/**
 * JWT configuration properties bound from application.yml (app.jwt.*).
 */
@Getter
@Setter
@Validated
@Configuration
@ConfigurationProperties(prefix = "app.jwt")
public class JwtProperties {

    /**
     * HMAC secret key for signing JWT tokens (HS256).
     * Must be provided via env var JWT_SECRET.
     */
    @NotBlank(message = "JWT_SECRET must be provided in the environment")
    @Size(min = 64, message = "JWT_SECRET must be at least 64 characters long for HS256")
    private String secret;

    /**
     * Token expiration time in milliseconds. Default: 24 hours.
     */
    private long expirationMs = 86_400_000L;
}
