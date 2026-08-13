package com.avaliance.copilot.mission.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.OffsetDateTime;

/**
 * DTO for mission responses (detail + list items).
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class MissionDto {

    private Long id;
    private String title;
    private String sector;
    private String missionType;
    private String[] technologies;
    private Integer year;
    private String referentTag;
    private String summary;
    private OffsetDateTime createdAt;
}
