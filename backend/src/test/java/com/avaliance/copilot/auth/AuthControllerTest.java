package com.avaliance.copilot.auth;

import com.avaliance.copilot.auth.dto.LoginRequest;
import com.avaliance.copilot.auth.dto.RegisterRequest;
import com.avaliance.copilot.auth.entity.AppUser;
import com.avaliance.copilot.auth.repository.AppUserRepository;
import com.avaliance.copilot.auth.service.JwtService;
import com.avaliance.copilot.config.enums.Role;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * Integration tests for AuthController: login, JWT, protected routes, register.
 */
@SpringBootTest
@AutoConfigureMockMvc
class AuthControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private AppUserRepository appUserRepository;

    @Autowired
    private PasswordEncoder passwordEncoder;

    @Autowired
    private JwtService jwtService;

    @BeforeEach
    void setUp() {
        appUserRepository.deleteAll();

        // Seed a test admin user
        AppUser admin = AppUser.builder()
                .username("admin")
                .passwordHash(passwordEncoder.encode("admin123"))
                .role(Role.ADMIN.name())
                .build();
        appUserRepository.save(admin);

        // Seed a test consultant user
        AppUser consultant = AppUser.builder()
                .username("consultant")
                .passwordHash(passwordEncoder.encode("consul123"))
                .role(Role.CONSULTANT.name())
                .build();
        appUserRepository.save(consultant);
    }

    @Test
    @DisplayName("POST /api/auth/login — valid credentials return JWT")
    void login_validCredentials_returnsJwt() throws Exception {
        LoginRequest request = new LoginRequest("admin", "admin123");

        MvcResult result = mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.token").isNotEmpty())
                .andExpect(jsonPath("$.username").value("admin"))
                .andExpect(jsonPath("$.role").value("ADMIN"))
                .andReturn();

        // Verify the returned token is valid
        String responseBody = result.getResponse().getContentAsString();
        String token = objectMapper.readTree(responseBody).get("token").asText();
        assertThat(jwtService.isTokenValid(token)).isTrue();
        assertThat(jwtService.extractUsername(token)).isEqualTo("admin");
        assertThat(jwtService.extractRole(token)).isEqualTo("ADMIN");
    }

    @Test
    @DisplayName("POST /api/auth/login — invalid credentials return 401")
    void login_invalidCredentials_returns401() throws Exception {
        LoginRequest request = new LoginRequest("admin", "wrongpassword");

        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("POST /api/auth/login — missing fields return 400")
    void login_missingFields_returns400() throws Exception {
        mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    @DisplayName("GET /api/missions — without token returns 401")
    void protectedRoute_noToken_returns401() throws Exception {
        mockMvc.perform(get("/api/missions"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @DisplayName("GET /api/missions — with valid token returns 200")
    void protectedRoute_withToken_returns200() throws Exception {
        String token = jwtService.generateToken("admin", Role.ADMIN.name());

        mockMvc.perform(get("/api/missions")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk());
    }

    @Test
    @DisplayName("GET /api/auth/users — ADMIN can list users without password hashes")
    void users_asAdmin_returnsSafeDirectory() throws Exception {
        String token = jwtService.generateToken("admin", Role.ADMIN.name());

        mockMvc.perform(get("/api/auth/users")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].username").value("admin"))
                .andExpect(jsonPath("$[0].role").value("ADMIN"))
                .andExpect(jsonPath("$[0].passwordHash").doesNotExist())
                .andExpect(jsonPath("$[1].username").value("consultant"));
    }

    @Test
    @DisplayName("GET /api/auth/users — CONSULTANT is forbidden")
    void users_asConsultant_returns403() throws Exception {
        String token = jwtService.generateToken("consultant", Role.CONSULTANT.name());

        mockMvc.perform(get("/api/auth/users")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("POST /api/auth/register — ADMIN can create user")
    void register_asAdmin_createsUser() throws Exception {
        String token = jwtService.generateToken("admin", Role.ADMIN.name());
        RegisterRequest request = new RegisterRequest("newuser", "password123", Role.CONSULTANT.name());

        mockMvc.perform(post("/api/auth/register")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.username").value("newuser"));

        assertThat(appUserRepository.existsByUsername("newuser")).isTrue();
    }

    @Test
    @DisplayName("POST /api/auth/register — CONSULTANT is forbidden")
    void register_asConsultant_returns403() throws Exception {
        String token = jwtService.generateToken("consultant", Role.CONSULTANT.name());
        RegisterRequest request = new RegisterRequest("anotheruser", "password123", Role.CONSULTANT.name());

        mockMvc.perform(post("/api/auth/register")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isForbidden());
    }

    @Test
    @DisplayName("POST /api/auth/register — duplicate username returns 400")
    void register_duplicateUsername_returns400() throws Exception {
        String token = jwtService.generateToken("admin", Role.ADMIN.name());
        RegisterRequest request = new RegisterRequest("admin", "password123", Role.CONSULTANT.name());

        mockMvc.perform(post("/api/auth/register")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }
}
