import { useState } from 'react'
import type { FormEvent } from 'react'
import type { RfpCitation } from '../types.ts'
import { ArrowUp, Check, Copy, Download, FilePenLine, Info, SlidersHorizontal } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import logoSrc from '../assets/logo.png'
import { api, errorMessage } from '../api/client.ts'
import { ErrorState } from '../components/AsyncState.tsx'
import { PageHeader } from '../components/PageHeader.tsx'
import { RfpProposalDocument } from '../components/RfpProposalDocument.tsx'
import { proposalToText } from '../components/rfpProposalText.ts'

export function RfpPage() {
  const [description, setDescription] = useState('')
  const [sector, setSector] = useState('')
  const [missionType, setMissionType] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [preview, setPreview] = useState<{ citation: RfpCitation; url: string } | null>(null)
  const generation = useMutation({ mutationFn: () => api.generateRfp({ description, sector: sector || undefined, missionType: missionType || undefined, topK: 5 }) })

  const submit = (event: FormEvent) => { event.preventDefault(); if (!generation.isPending) generation.mutate() }
  const retry = () => { generation.reset(); generation.mutate() }
  const proposalText = generation.data == null
    ? ''
    : proposalToText(generation.data.proposal)
  const copy = async () => { if (!proposalText) return; await navigator.clipboard.writeText(proposalText); setCopied(true); window.setTimeout(() => setCopied(false), 1600) }
  const openPdf = async (citation: RfpCitation) => {
    try {
      if (preview) URL.revokeObjectURL(preview.url)
      const url = URL.createObjectURL(await api.downloadDocument(citation.documentId))
      setPreview({ citation, url })
    } catch {
      // A preview failure must remain local to the RFP page.
    }
  }
  const download = () => {
    if (!proposalText) return
    const url = URL.createObjectURL(new Blob([proposalText], { type: 'text/plain;charset=utf-8' }))
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'proposition-avaliance.txt'; anchor.click(); URL.revokeObjectURL(url)
  }

  return (
    <div className="page page--rfp">
      <PageHeader eyebrow="Avant-vente" title="Construire une proposition" description="Générez un document de réponse structuré, exploitable et appuyé sur les missions comparables disponibles." />
      <form className="rfp-brief" onSubmit={submit} aria-busy={generation.isPending}>
        <header className="rfp-brief__header">
          <span className="rfp-brief__header-icon" aria-hidden="true"><FilePenLine size={17} /></span>
          <div>
            <span className="rfp-brief__kicker">Document de travail</span>
            <label htmlFor="rfp-description">Brief client ou cahier des charges</label>
          </div>
        </header>
        <div className="rfp-brief__body">
          <textarea id="rfp-description" rows={7} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Décrivez le contexte, les objectifs, le périmètre attendu et les contraintes de la mission…" required />
          <footer className="rfp-composer__footer">
            <div className="rfp-composer__chips">
              <button className="filter-toggle" type="button" aria-expanded={filtersOpen} aria-controls="rfp-advanced-filters" onClick={() => setFiltersOpen((open) => !open)}><SlidersHorizontal size={15} />Paramètres avancés</button>
            </div>
            <div className="rfp-composer__actions">
              <button className="button button--primary rfp-submit" type="submit" disabled={!description.trim() || generation.isPending} aria-label="Générer la proposition" title="Générer la proposition"><ArrowUp size={18} /></button>
            </div>
          </footer>
          <div id="rfp-advanced-filters" className={`filter-row rfp-filter-row ${filtersOpen ? 'filter-row--open' : ''}`}>
            <label>Secteur<input value={sector} onChange={(event) => setSector(event.target.value)} placeholder="Ex. banque" /></label>
            <label>Type de mission<input value={missionType} onChange={(event) => setMissionType(event.target.value)} placeholder="Ex. migration cloud" /></label>
          </div>
        </div>
      </form>
      <p className="rfp-guidance"><Info size={15} aria-hidden="true" /><span>Plus le brief est précis, plus la synthèse, les livrables, la démarche, les jalons et les questions de cadrage seront pertinents. Les références restent citées et les recommandations sont explicitement distinguées des faits établis.</span></p>
      {generation.isPending && <div className="rfp-status" role="status" aria-live="polite"><span className="rfp-status__avatar" aria-hidden="true"><img src={logoSrc} alt="" /></span><span className="rfp-status__label">Génération de la proposition…</span></div>}
      {generation.isError && <div className="rfp-error"><ErrorState message={errorMessage(generation.error)} /><button className="button button--secondary" type="button" onClick={retry}>Réessayer</button></div>}
      {!generation.data && !generation.isPending && !generation.isError && <section className="rfp-empty"><FilePenLine size={24} /><h2>Le document de travail apparaîtra ici.</h2><p>Les missions comparables resteront visibles pour faciliter la relecture, l’alignement et la vérification.</p></section>}
      {generation.data && (
        <section className="rfp-result reveal">
          <aside className="reference-list">
            <div className="section-heading"><span>Preuves PDF vérifiées</span><strong>{generation.data.citations.length.toString().padStart(2, '0')}</strong></div>
            {generation.data.citations.map((citation) => <article key={citation.citationId} className="reference-item"><span>[{citation.sourceIndex}]</span><div><h3>{citation.documentName}</h3><p>Page physique {citation.page} · Chunk {citation.chunkId}</p><blockquote>{citation.content}</blockquote><button className="link-button" type="button" onClick={() => void openPdf(citation)}>Voir dans le PDF</button></div></article>)}
            <div className="section-heading"><span>Missions synthétiques comparables</span><strong>{generation.data.similarMissions.length.toString().padStart(2, '0')}</strong></div>
            {generation.data.similarMissions.length === 0 ? <p className="rfp-no-match">Aucune mission suffisamment comparable.</p> : generation.data.similarMissions.map((mission) => <article key={mission.id} className="reference-item"><span>MS</span><div><h3>{mission.title}</h3><p>Mission synthétique · {mission.sector} · score {Math.round(mission.scoreBreakdown.finalScore * 100)}%</p><p>Secteur {Math.round(mission.scoreBreakdown.sectorMatch * 100)}% · besoin {Math.round(mission.scoreBreakdown.businessNeedMatch * 100)}% · contraintes {Math.round(mission.scoreBreakdown.constraintMatch * 100)}%</p></div></article>)}
          </aside>
          <article className="rfp-document">
            <header><div className="rfp-document__identity"><span className="rfp-document__identity-icon"><img src={logoSrc} alt="" /></span><div><span className="eyebrow">Proposition Avaliance</span><h2>{generation.data.proposal.title}</h2></div></div><div className="document-actions"><button className="icon-button" type="button" onClick={copy} title="Copier" aria-label="Copier">{copied ? <Check size={18} /> : <Copy size={18} />}</button><button className="icon-button" type="button" onClick={download} title="Télécharger" aria-label="Télécharger"><Download size={18} /></button></div></header>
            <span className="sr-only" role="status">{copied ? 'Proposition copiée.' : ''}</span>
            {!generation.data.evidenceValidationPassed && <div className="rfp-no-evidence">Aucune preuve PDF suffisamment pertinente n’a été retenue. La proposition formule donc des recommandations et des hypothèses, et non des faits établis.</div>}
            <RfpProposalDocument proposal={generation.data.proposal} evidence={generation.data.evidence} />
            <footer className="rfp-evidence-notes">{generation.data.evidence.map((item) => <p id={item.id} key={item.id}><strong>[p. {item.page}]</strong> {item.quote}</p>)}</footer>
          </article>
        </section>
      )}
      {preview && <section className="rfp-pdf-preview" aria-label="Aperçu du document source"><header><strong>{preview.citation.documentName} — page physique {preview.citation.page}</strong><button className="icon-button" type="button" onClick={() => { URL.revokeObjectURL(preview.url); setPreview(null) }} aria-label="Fermer l’aperçu">×</button></header><iframe title={preview.citation.documentName} src={`${preview.url}#page=${preview.citation.page}`} /></section>}
    </div>
  )
}