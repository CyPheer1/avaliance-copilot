package com.avaliance.copilot.integration;

import com.avaliance.copilot.auth.dto.LoginRequest;
import com.avaliance.copilot.auth.dto.RegisterRequest;
import com.avaliance.copilot.config.enums.Role;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * Validates the full authentication flow on a real PostgreSQL database.
 * Tests that the bootstrap admin was created successfully by AdminSeeder,
 * can log in, register a new user, and the new user can log in.
 */
@AutoConfigureMockMvc
class AuthFlowIT extends AbstractIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Test
    @DisplayName("Full auth flow: login as bootstrap admin -> register consultant -> login as consultant")
    void fullAuthFlow() throws Exception {
        // 1. Login as the bootstrap admin (seeded by AdminSeeder)
        LoginRequest adminLogin = new LoginRequest("admin", "admin123");
        
        MvcResult adminResult = mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(adminLogin)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.token").isNotEmpty())
                .andExpect(jsonPath("$.role").value(Role.ADMIN.name()))
                .andReturn();
                
        String adminToken = objectMapper.readTree(adminResult.getResponse().getContentAsString()).get("token").asText();

        // 2. Register a new consultant user
        RegisterRequest registerRequest = new RegisterRequest("newconsultant", "pass1234", Role.CONSULTANT.name());
        
        mockMvc.perform(post("/api/auth/register")
                        .header("Authorization", "Bearer " + adminToken)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(registerRequest)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.username").value("newconsultant"));

        // 3. Login as the new consultant
        LoginRequest consultantLogin = new LoginRequest("newconsultant", "pass1234");
        
        MvcResult consultantResult = mockMvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(consultantLogin)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.token").isNotEmpty())
                .andExpect(jsonPath("$.role").value(Role.CONSULTANT.name()))
                .andReturn();
                
        String consultantToken = objectMapper.readTree(consultantResult.getResponse().getContentAsString()).get("token").asText();

        // 4. Verify consultant can access protected routes
        mockMvc.perform(get("/api/missions")
                        .header("Authorization", "Bearer " + consultantToken))
                .andExpect(status().isOk());
    }
}
