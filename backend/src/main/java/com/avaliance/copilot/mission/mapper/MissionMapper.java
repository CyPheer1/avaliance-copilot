package com.avaliance.copilot.mission.mapper;

import com.avaliance.copilot.mission.dto.MissionDto;
import com.avaliance.copilot.mission.entity.Mission;
import org.springframework.stereotype.Component;

import java.util.Arrays;
import java.util.List;

@Component
public class MissionMapper {

    public MissionDto toDto(Mission entity) {
        if (entity == null) {
            return null;
        }

        return MissionDto.builder()
                .id(entity.getId())
                .title(entity.getTitle())
                .sector(entity.getSector())
                .missionType(entity.getMissionType())
                .technologies(entity.getTechnologies() != null ? entity.getTechnologies() : new String[0])
                .year(entity.getYear())
                .referentTag(entity.getReferentTag())
                .summary(entity.getSummary())
                .createdAt(entity.getCreatedAt())
                .build();
    }
}
