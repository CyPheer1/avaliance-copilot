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
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const generation = useMutation({ mutationFn: () => api.generateRfp({ description, mode: 'standard', sector: sector || undefined }) })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!generation.isPending) generation.mutate()
  }
  const retry = () => { generation.reset(); generation.mutate() }
  const response = generation.data
  const pending = generation.isPending
  const activeError = generation.error
  const activeErrorMessage = activeError ? errorMessage(activeError) : ''
  const proposalText = response == null
    ? ''
    : proposalToText(response.proposal)
  const expectedSectionCount = 6
  const sectionCount = response?.proposal?.sections?.length ?? 0
  const visibleSectionCount = Math.min(sectionCount, expectedSectionCount)
  const sourceCount = response?.sources?.length ?? 0
  const qualityLabel = response?.quality?.passed && response?.evidenceValidationPassed ? 'Prêt à valider' : 'À compléter'
  const copy = async () => { if (!proposalText) return; await navigator.clipboard.writeText(proposalText); setCopied(true); window.setTimeout(() => setCopied(false), 1600) }
  const download = () => {
    if (!proposalText) return
    const url = URL.createObjectURL(new Blob([proposalText], { type: 'text/plain;charset=utf-8' }))
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'proposition-avaliance.txt'; anchor.click(); URL.revokeObjectURL(url)
  }

  return (
    <div className="page page--rfp">
      <PageHeader eyebrow="Avant-vente" title="Construire une proposition" description="Générez un document de réponse structuré, exploitable et appuyé exclusivement sur les PDF uploadés et indexés sur la plateforme." />
      <form className="rfp-brief" onSubmit={submit} aria-busy={pending}>
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
              <span className="rfp-brief__counter">{description.length > 0 ? `${description.length} caractères` : 'Brief à renseigner'}</span>
              <button className="filter-toggle" type="button" aria-expanded={filtersOpen} aria-controls="rfp-advanced-filters" onClick={() => setFiltersOpen((open) => !open)}><SlidersHorizontal size={15} />Paramètres avancés</button>
            </div>
            <div className="rfp-composer__actions">
              <button className="button button--primary rfp-submit" type="submit" disabled={!description.trim() || pending} aria-label="Générer la proposition" title="Générer la proposition"><ArrowUp size={18} /></button>
            </div>
          </footer>
          <div id="rfp-advanced-filters" className={`filter-row rfp-filter-row ${filtersOpen ? 'filter-row--open' : ''}`}>
            <label>Secteur<input value={sector} onChange={(event) => setSector(event.target.value)} placeholder="Ex. banque" /></label>
          </div>
        </div>
      </form>
      <p className="rfp-guidance"><Info size={15} aria-hidden="true" /><span>Plus le brief est précis, plus la synthèse, les livrables, la démarche, les jalons et les questions de cadrage seront pertinents. Les références restent citées et les recommandations sont explicitement distinguées des faits établis.</span></p>
      {pending && <div className="rfp-status" role="status" aria-live="polite"><span className="rfp-status__avatar" aria-hidden="true"><img src={logoSrc} alt="" /></span><span className="rfp-status__label">Génération de la proposition…</span></div>}
      {Boolean(activeError) && <div className="rfp-error"><ErrorState message={activeErrorMessage} /><button className="button button--secondary" type="button" onClick={retry}>Réessayer</button></div>}
      {!response && !pending && !activeError && <section className="rfp-empty"><FilePenLine size={24} /><h2>Le document de travail apparaîtra ici.</h2><p>Le document structuré en {expectedSectionCount} sections et ses preuves PDF apparaîtront ici pour vérification.</p></section>}
      {response && (
        <section className="rfp-result reveal">
          <div className="rfp-result__overview" aria-label="Résumé de la proposition">
            <article className="rfp-kpi-card rfp-kpi-card--primary">
              <span className="rfp-kpi-card__label">Sections produites</span>
              <strong>{visibleSectionCount}<small>/{expectedSectionCount}</small></strong>
              <span className="rfp-kpi-card__hint">Structure de réponse</span>
            </article>
            <article className="rfp-kpi-card">
              <span className="rfp-kpi-card__label">Références PDF</span>
              <strong>{sourceCount}</strong>
              <span className="rfp-kpi-card__hint">Sources internes retenues</span>
            </article>
            <article className="rfp-kpi-card">
              <span className="rfp-kpi-card__label">Validation</span>
              <strong className={qualityLabel === 'Prêt à valider' ? 'rfp-kpi-card__value--success' : 'rfp-kpi-card__value--warning'}>{qualityLabel}</strong>
              <span className="rfp-kpi-card__hint">Contrôle des preuves</span>
            </article>
            <article className="rfp-kpi-card">
              <span className="rfp-kpi-card__label">Format</span>
              <strong>PDF</strong>
              <span className="rfp-kpi-card__hint">Réponse documentée</span>
            </article>
          </div>
          <article className="rfp-document">
            <header>
              <div className="rfp-document__identity">
                <span className="rfp-document__identity-icon">
                  <img src={logoSrc} alt="" />
                </span>
                <div>
                  <span className="eyebrow">Proposition Enterprise Avaliance</span>
                  <h2>{response.proposal.title}</h2>
                  <div className="rfp-quality-meta">
                    {response.requestId && (
                      <span><strong>ID Requête :</strong> <code className="rfp-request-id">{response.requestId}</code></span>
                    )}
                    <span><strong>Sections :</strong> {response.proposal?.sections ? `${visibleSectionCount}/6` : 'Non calculé'}</span>
                    <span><strong>État :</strong> {response.quality?.passed ? 'Validé' : 'À compléter'}</span>
                    {response.sources && response.sources.length > 0 && (
                      <span><strong>Références PDF :</strong> {response.sources.length}</span>
                    )}
                    {!response.evidenceValidationPassed && (response.sources?.length ?? 0) === 0 && <span className="rfp-meta-warning"><strong>Références :</strong> à compléter</span>}
                  </div>
                  {(!response.quality?.passed || !response.evidenceValidationPassed) && (
                    <div className="rfp-warnings-list">
                      <strong>À compléter avant envoi :</strong>
                      <ul style={{ margin: '0.25rem 0 0 1rem', padding: 0 }}>
                        {(response.sources?.length ?? 0) === 0 && <li>Aucune référence PDF pertinente n’a été retenue pour ce brief.</li>}
                        {(response.sources?.length ?? 0) > 0 && !response.evidenceValidationPassed && <li>Les références PDF soutiennent les recommandations ; les faits propres au client restent à confirmer.</li>}
                        {!response.quality?.passed && <li>Le contenu actuel est un brouillon fondé sur le brief client, à valider avant envoi.</li>}
                      </ul>
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
            {!response.evidenceValidationPassed && (
              <div className="rfp-no-evidence">
                {sourceCount === 0
                  ? 'Aucune preuve PDF interne pertinente n’a été trouvée dans la base interne pour ce brief. Les recommandations restent à confirmer avant envoi.'
                  : 'Cette proposition distingue les faits du brief et les références internes. Les faits propres au client restent à confirmer avant envoi.'}
              </div>
            )}
            <RfpProposalDocument proposal={response.proposal} />
          </article>
        </section>
      )}
    </div>
  )
}