package com.avaliance.copilot.mission.controller;

import com.avaliance.copilot.mission.dto.MissionDto;
import com.avaliance.copilot.mission.service.MissionService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/missions")
@RequiredArgsConstructor
public class MissionController {

    private final MissionService missionService;

    @GetMapping
    public ResponseEntity<Page<MissionDto>> getMissions(
            @RequestParam(required = false) String sector,
            @RequestParam(required = false) String missionType,
            @RequestParam(required = false) Integer year,
            Pageable pageable) {
        
        Page<MissionDto> page = missionService.getMissions(sector, missionType, year, pageable);
        return ResponseEntity.ok(page);
    }

    @GetMapping("/{id}")
    public ResponseEntity<MissionDto> getMission(@PathVariable Long id) {
        return ResponseEntity.ok(missionService.getMissionById(id));
    }
}
