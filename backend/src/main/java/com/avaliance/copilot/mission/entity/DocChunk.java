package com.avaliance.copilot.mission.entity;

import jakarta.persistence.*;
import lombok.*;


@Entity
@Table(name = "doc_chunk")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class DocChunk {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "mission_id")
    private Long missionId;

    @Column(name = "chunk_index", nullable = false)
    private Integer chunkIndex;

    @Column(nullable = false, columnDefinition = "text")
    private String content;

    private String sector;

    @Column(name = "mission_type")
    private String missionType;

    @Column
    private String[] technologies;

    @Column(name = "\"year\"")
    private Integer year;

}
