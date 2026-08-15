import { useState } from 'react'
import type { FormEvent } from 'react'
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
  const generation = useMutation({ mutationFn: () => api.generateRfp({ description, sector: sector || undefined, missionType: missionType || undefined, topK: 5 }) })

  const submit = (event: FormEvent) => { event.preventDefault(); if (!generation.isPending) generation.mutate() }
  const retry = () => { generation.reset(); generation.mutate() }
  const proposalText = generation.data == null
    ? ''
    : proposalToText(generation.data.proposal)
  const copy = async () => { if (!proposalText) return; await navigator.clipboard.writeText(proposalText); setCopied(true); window.setTimeout(() => setCopied(false), 1600) }
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
          <article className="rfp-document">
            <header>
              <div className="rfp-document__identity">
                <span className="rfp-document__identity-icon">
                  <img src={logoSrc} alt="" />
                </span>
                <div>
                  <span className="eyebrow">Proposition Enterprise Avaliance</span>
                  <h2>{generation.data.proposal.title}</h2>
                  {generation.data.quality && (
                    <div className="rfp-quality-meta" style={{ display: 'flex', gap: '0.75rem', marginTop: '0.25rem', fontSize: '0.8125rem', color: '#64748b' }}>
                      <span><strong>Sections :</strong> {generation.data.proposal.sections.length}/19</span>
                      <span><strong>Indice de conformité :</strong> {Math.round(generation.data.quality.score * 100)}%</span>
                      {generation.data.sources && generation.data.sources.length > 0 && (
                        <span><strong>Preuves PDF :</strong> {generation.data.sources.length} document(s)</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
              <div className="document-actions">
                <button className="icon-button" type="button" onClick={copy} title="Copier" aria-label="Copier">
                  {copied ? <Check size={18} /> : <Copy size={18} />}
                </button>
                <button className="icon-button" type="button" onClick={download} title="Télécharger (.txt)" aria-label="Télécharger">
                  <Download size={18} />
                </button>
              </div>
            </header>
            <span className="sr-only" role="status">
              {copied ? 'Proposition copiée.' : ''}
            </span>
            {!generation.data.evidenceValidationPassed && (
              <div className="rfp-no-evidence">
                Aucune preuve PDF suffisamment pertinente n’a été retenue dans la base interne. La proposition formule donc des recommandations méthodologiques, des hypothèses et des questions de cadrage issues du brief client.
              </div>
            )}
            <RfpProposalDocument proposal={generation.data.proposal} />
          </article>
        </section>
      )}
    </div>
  )
}