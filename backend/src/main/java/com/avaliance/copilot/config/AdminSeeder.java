package com.avaliance.copilot.config;

import com.avaliance.copilot.auth.entity.AppUser;
import com.avaliance.copilot.auth.repository.AppUserRepository;
import com.avaliance.copilot.config.enums.Role;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.CommandLineRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * Seeds or synchronizes the bootstrap admin user on startup.
 * Reads credentials from environment variables to avoid hardcoded secrets.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class AdminSeeder implements CommandLineRunner {

    private final AdminProperties adminProperties;
    private final AppUserRepository appUserRepository;
    private final PasswordEncoder passwordEncoder;

    @Override
    public void run(String... args) {
        String username = adminProperties.getUsername();
        AppUser admin = appUserRepository.findByUsername(username).orElse(null);
        if (admin != null) {
            boolean passwordChanged = !passwordEncoder.matches(adminProperties.getPassword(), admin.getPasswordHash());
            boolean roleChanged = !Role.ADMIN.name().equals(admin.getRole());
            if (!passwordChanged && !roleChanged) {
                log.info("Bootstrap admin user '{}' is already synchronized.", username);
                return;
            }

            if (passwordChanged) {
                admin.setPasswordHash(passwordEncoder.encode(adminProperties.getPassword()));
            }
            admin.setRole(Role.ADMIN.name());
            appUserRepository.save(admin);
            log.info("Bootstrap admin user '{}' synchronized from configuration.", username);
            return;
        }

        log.info("Seeding bootstrap admin user '{}'...", username);
        admin = AppUser.builder()
                .username(username)
                .passwordHash(passwordEncoder.encode(adminProperties.getPassword()))
                .role(Role.ADMIN.name())
                .build();

        appUserRepository.save(admin);
        log.info("Admin user '{}' created successfully.", username);
    }
}
