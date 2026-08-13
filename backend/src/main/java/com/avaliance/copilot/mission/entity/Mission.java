package com.avaliance.copilot.mission.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.OffsetDateTime;

@Entity
@Table(name = "mission")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Mission {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @Column(nullable = false)
    private String sector;

    @Column(name = "mission_type", nullable = false)
    private String missionType;

    @Column(nullable = false)
    private String[] technologies;

    @Column(name = "\"year\"", nullable = false)
    private Integer year;

    @Column(name = "referent_tag")
    private String referentTag;

    @Column(nullable = false, columnDefinition = "text")
    private String summary;

    @Column(name = "created_at", insertable = false, updatable = false)
    private OffsetDateTime createdAt;
}
