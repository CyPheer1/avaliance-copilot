package com.avaliance.copilot.audit.service;

import com.avaliance.copilot.audit.entity.AuditLog;
import com.avaliance.copilot.audit.repository.AuditLogRepository;
import com.avaliance.copilot.auth.entity.AppUser;
import com.avaliance.copilot.auth.repository.AppUserRepository;
import com.avaliance.copilot.config.enums.AuditAction;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

/**
 * Service for recording audit log entries.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AuditService {

    private final AuditLogRepository auditLogRepository;
    private final AppUserRepository appUserRepository;

    /**
     * Record an audit entry with status and duration.
     *
     * @param action     the action type
     * @param queryText  the user's query text
     * @param status     SUCCESS or ERROR
     * @param durationMs duration in milliseconds
     */
    public void log(AuditAction action, String queryText, String status, Long durationMs) {
        Long userId = resolveCurrentUserId();

        AuditLog entry = AuditLog.builder()
                .userId(userId)
                .action(action.name())
                .queryText(queryText)
                .status(status)
                .durationMs(durationMs)
                .build();

        auditLogRepository.save(entry);
        log.debug("Audit: user={} action={} query={} status={} duration={}ms",
                userId, action, queryText, status, durationMs);
    }

    /**
     * Legacy method for backward compatibility. Assumes SUCCESS and no duration.
     */
    public void log(String actionStr, String queryText) {
        AuditAction action;
        try {
            action = AuditAction.valueOf(actionStr);
        } catch (IllegalArgumentException e) {
            log.warn("Unknown audit action: {}", actionStr);
            return;
        }
        log(action, queryText, "SUCCESS", null);
    }

    private Long resolveCurrentUserId() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || auth.getPrincipal() == null) {
            return null;
        }
        String username = auth.getPrincipal().toString();
        return appUserRepository.findByUsername(username)
                .map(AppUser::getId)
                .orElse(null);
    }
}
