package com.avaliance.copilot.mission.service;

import com.avaliance.copilot.mission.dto.MissionDto;
import com.avaliance.copilot.mission.entity.Mission;
import com.avaliance.copilot.mission.mapper.MissionMapper;
import com.avaliance.copilot.mission.repository.MissionRepository;
import jakarta.persistence.EntityNotFoundException;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class MissionService {

    private final MissionRepository missionRepository;
    private final MissionMapper missionMapper;

    @Transactional(readOnly = true)
    public Page<MissionDto> getMissions(String sector, String missionType, Integer year, Pageable pageable) {
        Page<Mission> page = missionRepository.findByFilters(sector, missionType, year, pageable);
        return page.map(missionMapper::toDto);
    }

    @Transactional(readOnly = true)
    public MissionDto getMissionById(Long id) {
        Mission mission = missionRepository.findById(id)
                .orElseThrow(() -> new EntityNotFoundException("Mission not found with ID: " + id));
        return missionMapper.toDto(mission);
    }
}
