import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, CalendarDays, Layers3, UserRound } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client.ts'
import { ErrorState } from '../components/AsyncState.tsx'

export function MissionDetailPage() {
  const { missionId } = useParams()
  const id = Number(missionId)
  const mission = useQuery({ queryKey: ['mission', id], queryFn: () => api.mission(id), enabled: Number.isFinite(id) })
  if (mission.isLoading) return <div className="page"><div className="table-loading">Ouverture du dossier de référence…</div></div>
  if (mission.isError) return <div className="page"><ErrorState message={errorMessage(mission.error)} /></div>
  if (!mission.data) return null

  return (
    <div className="page mission-detail reveal">
      <Link className="back-link" to="/missions"><ArrowLeft size={16} />Retour au référentiel</Link>
      <header className="mission-dossier-header"><div><span className="eyebrow">Dossier M-{String(mission.data.id).padStart(4, '0')}</span><h1>{mission.data.title}</h1></div><strong>{mission.data.year}</strong></header>
      <div className="mission-facts"><div><Layers3 size={18} /><span>Secteur</span><strong>{mission.data.sector}</strong></div><div><CalendarDays size={18} /><span>Type de mission</span><strong>{mission.data.missionType}</strong></div><div><UserRound size={18} /><span>Profil référent</span><strong>{mission.data.referentTag ?? 'À préciser'}</strong></div></div>
      <section className="dossier-section"><span className="section-number">01</span><div><span className="eyebrow">Synthèse</span><p className="mission-summary">{mission.data.summary}</p></div></section>
      <section className="dossier-section"><span className="section-number">02</span><div><span className="eyebrow">Socle technologique</span><div className="technology-grid">{mission.data.technologies.map((technology) => <span key={technology}>{technology}</span>)}</div></div></section>
    </div>
  )
}