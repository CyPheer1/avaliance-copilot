package com.avaliance.copilot.mission.repository;

import com.avaliance.copilot.mission.entity.Mission;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface MissionRepository extends JpaRepository<Mission, Long> {

        interface LabelCountProjection {
                String getLabel();
                Long getTotal();
        }

        interface YearCountProjection {
                Integer getYear();
                Long getTotal();
        }

    @Query("SELECT m FROM Mission m WHERE " +
            "(:sector IS NULL OR m.sector = :sector) AND " +
            "(:missionType IS NULL OR m.missionType = :missionType) AND " +
            "(:year IS NULL OR m.year = :year)")
    Page<Mission> findByFilters(
            @Param("sector") String sector,
            @Param("missionType") String missionType,
            @Param("year") Integer year,
            Pageable pageable
    );

        @Query("SELECT m.sector AS label, COUNT(m) AS total FROM Mission m GROUP BY m.sector ORDER BY total DESC")
        List<LabelCountProjection> countBySector();

        @Query("SELECT m.missionType AS label, COUNT(m) AS total FROM Mission m GROUP BY m.missionType ORDER BY total DESC")
        List<LabelCountProjection> countByMissionType();

        @Query("SELECT m.year AS year, COUNT(m) AS total FROM Mission m GROUP BY m.year ORDER BY m.year")
        List<YearCountProjection> countByYear();
}
