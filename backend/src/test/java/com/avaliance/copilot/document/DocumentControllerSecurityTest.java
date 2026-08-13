package com.avaliance.copilot.document;

import com.avaliance.copilot.auth.service.JwtService;
import com.avaliance.copilot.config.enums.Role;
import com.avaliance.copilot.document.service.DocumentService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DocumentControllerSecurityTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JwtService jwtService;

    @MockBean
    private DocumentService documentService;

    @Test
    void downloadWithoutAuthenticationReturns401() throws Exception {
        mockMvc.perform(get("/api/documents/42/content"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void downloadAsConsultantReturns403() throws Exception {
        String token = jwtService.generateToken("consultant", Role.CONSULTANT.name());

        mockMvc.perform(get("/api/documents/42/content")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                .andExpect(status().isForbidden());
    }

    @Test
    void downloadAsAdminReturns200AndOriginalBytes() throws Exception {
        String token = jwtService.generateToken("admin", Role.ADMIN.name());
        byte[] original = "document original".getBytes();
        when(documentService.download(42L)).thenReturn(new DocumentService.DownloadedDocument(
                new ByteArrayResource(original), "mission.pdf", "application/pdf"));

        mockMvc.perform(get("/api/documents/42/content")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"mission.pdf\""))
                .andExpect(content().contentType("application/pdf"))
                .andExpect(content().bytes(original));
    }
}
