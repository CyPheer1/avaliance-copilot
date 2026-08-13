import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, ArrowUpRight, Database } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, errorMessage } from '../api/client.ts'
import { ErrorState } from '../components/AsyncState.tsx'
import { PageHeader } from '../components/PageHeader.tsx'

export function MissionsPage() {
  const [page, setPage] = useState(0)
  const [sector, setSector] = useState('')
  const [missionType, setMissionType] = useState('')
  const [year, setYear] = useState('')
  const params = new URLSearchParams({ page: String(page), size: '12', sort: 'year,desc' })
  if (sector) params.set('sector', sector)
  if (missionType) params.set('missionType', missionType)
  if (year) params.set('year', year)
  const missions = useQuery({ queryKey: ['missions', page, sector, missionType, year], queryFn: () => api.missions(params) })

  return (
    <div className="page">
      <PageHeader eyebrow="Base de connaissances" title="Référentiel des missions" description="Parcourez les références synthétiques mobilisées par la recherche et la génération assistée." action={missions.data && <div className="record-count"><strong>{missions.data.totalElements}</strong><span>missions indexées</span></div>} />
      <div className="mission-filters">
        <label>Secteur<input value={sector} onChange={(event) => { setSector(event.target.value); setPage(0) }} placeholder="Tous" /></label>
        <label>Type<input value={missionType} onChange={(event) => { setMissionType(event.target.value); setPage(0) }} placeholder="Tous" /></label>
        <label>Année<input type="number" value={year} onChange={(event) => { setYear(event.target.value); setPage(0) }} placeholder="Toutes" /></label>
      </div>
      {missions.isLoading && <div className="table-loading">Chargement du référentiel…</div>}
      {missions.isError && <ErrorState message={errorMessage(missions.error)} />}
      {missions.data?.empty && <div className="empty-table"><Database size={22} /><p>Aucune mission ne correspond à la sélection en cours.</p></div>}
      {missions.data && !missions.data.empty && (
        <>
          <div className="mission-table" role="table">
            <div className="mission-row mission-row--head" role="row"><span role="columnheader">Mission</span><span role="columnheader">Secteur / type</span><span role="columnheader">Stack</span><span role="columnheader">Année</span><span role="columnheader" aria-label="Actions" /></div>
            {missions.data.content.map((mission) => <div className="mission-row" role="row" key={mission.id}><div role="cell"><span className="mission-id">M-{String(mission.id).padStart(4, '0')}</span><strong>{mission.title}</strong><p>{mission.summary}</p></div><div role="cell"><strong>{mission.sector}</strong><span>{mission.missionType}</span></div><div role="cell" className="tech-list">{mission.technologies.slice(0, 3).map((technology) => <i key={technology}>{technology}</i>)}</div><strong role="cell" className="mission-year">{mission.year}</strong><div role="cell"><Link className="icon-button" to={`/missions/${mission.id}`} title="Ouvrir" aria-label={`Ouvrir ${mission.title}`}><ArrowUpRight size={17} /></Link></div></div>)}
          </div>
          <footer className="pagination"><span>Page {missions.data.number + 1} sur {missions.data.totalPages}</span><div><button className="icon-button" type="button" disabled={missions.data.first} onClick={() => setPage((value) => value - 1)} title="Page précédente" aria-label="Page précédente"><ArrowLeft size={18} /></button><button className="icon-button" type="button" disabled={missions.data.last} onClick={() => setPage((value) => value + 1)} title="Page suivante" aria-label="Page suivante"><ArrowRight size={18} /></button></div></footer>
        </>
      )}
    </div>
  )
}