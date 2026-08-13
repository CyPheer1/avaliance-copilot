package com.avaliance.copilot.config;

import com.avaliance.copilot.auth.entity.AppUser;
import com.avaliance.copilot.auth.repository.AppUserRepository;
import com.avaliance.copilot.config.enums.Role;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AdminSeederTest {

    @Mock
    private AppUserRepository repository;

    @Mock
    private PasswordEncoder passwordEncoder;

    private AdminProperties properties;
    private AdminSeeder seeder;

    @BeforeEach
    void setUp() {
        properties = new AdminProperties();
        properties.setUsername("admin");
        properties.setPassword("configured-password");
        seeder = new AdminSeeder(properties, repository, passwordEncoder);
    }

    @Test
    void synchronizesExistingBootstrapAdminCredentialsAndRole() {
        AppUser admin = AppUser.builder()
                .username("admin")
                .passwordHash("stale-hash")
                .role(Role.CONSULTANT.name())
                .build();
        when(repository.findByUsername("admin")).thenReturn(Optional.of(admin));
        when(passwordEncoder.matches("configured-password", "stale-hash")).thenReturn(false);
        when(passwordEncoder.encode("configured-password")).thenReturn("current-hash");

        seeder.run();

        assertThat(admin.getPasswordHash()).isEqualTo("current-hash");
        assertThat(admin.getRole()).isEqualTo(Role.ADMIN.name());
        verify(repository).save(admin);
    }

    @Test
    void leavesMatchingBootstrapAdminUnchanged() {
        AppUser admin = AppUser.builder()
                .username("admin")
                .passwordHash("current-hash")
                .role(Role.ADMIN.name())
                .build();
        when(repository.findByUsername("admin")).thenReturn(Optional.of(admin));
        when(passwordEncoder.matches("configured-password", "current-hash")).thenReturn(true);

        seeder.run();

        verify(repository, never()).save(admin);
    }
}