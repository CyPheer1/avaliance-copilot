package com.avaliance.copilot.config;

import jakarta.validation.constraints.NotBlank;
import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.annotation.Validated;

/**
 * Configuration properties for the bootstrap admin user.
 * Validates that admin credentials are provided via environment variables.
 */
@Getter
@Setter
@Validated
@Configuration
@ConfigurationProperties(prefix = "app.admin")
public class AdminProperties {

    @NotBlank(message = "ADMIN_USERNAME must be provided")
    private String username;

    @NotBlank(message = "ADMIN_PASSWORD must be provided")
    private String password;
}
