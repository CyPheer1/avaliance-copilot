package com.avaliance.copilot.dashboard.controller;

import com.avaliance.copilot.dashboard.dto.DashboardSummary;
import com.avaliance.copilot.dashboard.service.DashboardService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/dashboard")
@RequiredArgsConstructor
public class DashboardController {

    private final DashboardService dashboardService;

    @GetMapping("/summary")
    public DashboardSummary summary(@RequestParam(defaultValue = "30") int days) {
        return dashboardService.getSummary(days);
    }
}