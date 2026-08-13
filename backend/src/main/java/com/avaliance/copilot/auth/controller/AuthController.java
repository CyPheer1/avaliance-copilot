package com.avaliance.copilot.auth.controller;

import com.avaliance.copilot.auth.dto.LoginRequest;
import com.avaliance.copilot.auth.dto.LoginResponse;
import com.avaliance.copilot.auth.dto.RegisterRequest;
import com.avaliance.copilot.auth.dto.UserResponse;
import com.avaliance.copilot.auth.entity.AppUser;
import com.avaliance.copilot.auth.repository.AppUserRepository;
import com.avaliance.copilot.auth.service.JwtService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

/**
 * Authentication endpoints: login (public) and register (ADMIN only).
 */
@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthenticationManager authenticationManager;
    private final JwtService jwtService;
    private final AppUserRepository appUserRepository;
    private final PasswordEncoder passwordEncoder;

    
    @PostMapping("/login")
    public ResponseEntity<LoginResponse> login(@Valid @RequestBody LoginRequest request) {
        Authentication authentication = authenticationManager.authenticate(
                new UsernamePasswordAuthenticationToken(request.getUsername(), request.getPassword())
        );

        AppUser user = appUserRepository.findByUsername(request.getUsername())
                .orElseThrow(); 

        String token = jwtService.generateToken(user.getUsername(), user.getRole());

        return ResponseEntity.ok(new LoginResponse(token, user.getUsername(), user.getRole()));
    }

    @GetMapping("/users")
    @PreAuthorize("hasRole('ADMIN')")
    public List<UserResponse> users() {
        return appUserRepository.findAll(Sort.by(Sort.Direction.ASC, "id")).stream()
                .map(user -> new UserResponse(user.getId(), user.getUsername(), user.getRole()))
                .toList();
    }

    
    @PostMapping("/register")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, String>> register(@Valid @RequestBody RegisterRequest request) {
        if (appUserRepository.existsByUsername(request.getUsername())) {
            throw new IllegalArgumentException("Username already exists: " + request.getUsername());
        }

        AppUser user = AppUser.builder()
                .username(request.getUsername())
                .passwordHash(passwordEncoder.encode(request.getPassword()))
                .role(request.getRole())
                .build();

        appUserRepository.save(user);

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("message", "User created", "username", user.getUsername()));
    }
}
