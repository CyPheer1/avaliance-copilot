import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import type { RfpResponse } from '../types.ts'
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
  const [mode, setMode] = useState<'standard' | 'brief' | 'full'>('standard')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [fullJobId, setFullJobId] = useState<string | null>(null)
  const [fullResponse, setFullResponse] = useState<RfpResponse | null>(null)
  const [fullJobError, setFullJobError] = useState<unknown>(null)
  const generation = useMutation({ mutationFn: () => api.generateRfp({ description, mode, sector: sector || undefined }) })
  const fullJob = useMutation({ mutationFn: () => api.createRfpJob({ description, sector: sector || undefined }) })

  useEffect(() => {
    if (!fullJobId) return
    let disposed = false
    const poll = async () => {
      try {
        const job = await api.rfpJob(fullJobId)
        if (disposed) return
        if (job.status === 'completed') { setFullResponse(await api.rfpJobResult(fullJobId)); return }
        if (job.status === 'failed' || job.status === 'cancelled') { setFullJobError(new Error(job.errorMessageSafe || `Le job a été ${job.status}.`)); return }
        window.setTimeout(poll, 2_000)
      } catch (error) { if (!disposed) setFullJobError(error) }
    }
    void poll()
    return () => { disposed = true }
  }, [fullJobId])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setFullResponse(null); setFullJobError(null); setFullJobId(null)
    if (mode === 'full') fullJob.mutate(undefined, { onSuccess: accepted => setFullJobId(accepted.jobId) })
    else if (!generation.isPending) generation.mutate()
  }
  const retry = () => { generation.reset(); fullJob.reset(); setFullJobError(null); if (mode === 'full') fullJob.mutate(undefined, { onSuccess: accepted => setFullJobId(accepted.jobId) }); else generation.mutate() }
  const response = generation.data ?? fullResponse
  const pending = generation.isPending || fullJob.isPending || Boolean(fullJobId && !fullResponse && !fullJobError)
  const activeError = generation.error ?? fullJob.error ?? fullJobError
  const activeErrorMessage = activeError ? errorMessage(activeError) : ''
  const proposalText = response == null
    ? ''
    : proposalToText(response.proposal)
  const expectedSectionCount = mode === 'brief' ? 4 : mode === 'full' ? 19 : 6
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
              <button className="filter-toggle" type="button" aria-expanded={filtersOpen} aria-controls="rfp-advanced-filters" onClick={() => setFiltersOpen((open) => !open)}><SlidersHorizontal size={15} />Paramètres avancés</button>
            </div>
            <div className="rfp-composer__actions">
              <button className="button button--primary rfp-submit" type="submit" disabled={!description.trim() || pending} aria-label="Générer la proposition" title="Générer la proposition"><ArrowUp size={18} /></button>
            </div>
          </footer>
          <div id="rfp-advanced-filters" className={`filter-row rfp-filter-row ${filtersOpen ? 'filter-row--open' : ''}`}>
            <label>Secteur<input value={sector} onChange={(event) => setSector(event.target.value)} placeholder="Ex. banque" /></label>
            <label>Mode de génération
              <select value={mode} onChange={(event) => setMode(event.target.value as 'standard' | 'brief' | 'full')}>
                <option value="standard">Standard (6 sections)</option>
                <option value="brief">Brief (4 sections)</option>
                <option value="full">Complète (19 sections - expérimental)</option>
              </select>
            </label>
          </div>
        </div>
      </form>
      <p className="rfp-guidance"><Info size={15} aria-hidden="true" /><span>Plus le brief est précis, plus la synthèse, les livrables, la démarche, les jalons et les questions de cadrage seront pertinents. Les références restent citées et les recommandations sont explicitement distinguées des faits établis.</span></p>
      {pending && <div className="rfp-status" role="status" aria-live="polite"><span className="rfp-status__avatar" aria-hidden="true"><img src={logoSrc} alt="" /></span><span className="rfp-status__label">{fullJobId ? `Génération complète en cours (job ${fullJobId})…` : 'Génération de la proposition…'}</span>{fullJobId && <button className="button button--secondary" type="button" onClick={() => void api.cancelRfpJob(fullJobId).then(() => setFullJobError(new Error('La génération a été annulée.')))}>Annuler</button>}</div>}
      {Boolean(activeError) && <div className="rfp-error"><ErrorState message={activeErrorMessage} /><button className="button button--secondary" type="button" onClick={retry}>Réessayer</button></div>}
      {!response && !pending && !activeError && <section className="rfp-empty"><FilePenLine size={24} /><h2>Le document de travail apparaîtra ici.</h2><p>Le document structuré en {expectedSectionCount} sections et ses preuves PDF apparaîtront ici pour vérification.</p></section>}
      {response && (
        <section className="rfp-result reveal">
          <article className="rfp-document">
            <header>
              <div className="rfp-document__identity">
                <span className="rfp-document__identity-icon">
                  <img src={logoSrc} alt="" />
                </span>
                <div>
                  <span className="eyebrow">Proposition Enterprise Avaliance</span>
                  <h2>{response.proposal.title}</h2>
                  <div className="rfp-quality-meta" style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginTop: '0.25rem', fontSize: '0.8125rem', color: '#64748b' }}>
                    {response.requestId && (
                      <span><strong>ID Requête :</strong> <code style={{ fontSize: '0.75rem', background: '#f1f5f9', padding: '0.125rem 0.25rem', borderRadius: '3px' }}>{response.requestId}</code></span>
                    )}
                    <span><strong>Sections :</strong> {response.proposal?.sections ? `${response.proposal.sections.length}/${response.mode === 'brief' ? 4 : response.mode === 'full' ? 19 : 6}` : 'Non calculé'}</span>
                    <span><strong>Indice de conformité :</strong> {response.quality?.score != null ? `${Math.round(response.quality.score * 100)}%` : 'Non calculé'}</span>
                    {response.sources && response.sources.length > 0 && (
                      <span><strong>Preuves PDF :</strong> {response.sources.length} document(s)</span>
                    )}
                    {response.quality?.warnings && response.quality.warnings.length > 0 && (
                      <span style={{ color: '#eab308' }} title={response.quality.warnings.join('\n')}>
                        <strong>Avertissements :</strong> {response.quality.warnings.length}
                      </span>
                    )}
                  </div>
                  {response.quality?.warnings && response.quality.warnings.length > 0 && (
                    <div className="rfp-warnings-list" style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: '#b45309', background: '#fef3c7', padding: '0.375rem 0.625rem', borderRadius: '4px' }}>
                      <strong>Avertissements qualité :</strong>
                      <ul style={{ margin: '0.25rem 0 0 1rem', padding: 0 }}>
                        {response.quality.warnings.map((w, idx) => (
                          <li key={idx}>{w}</li>
                        ))}
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
                Aucune preuve PDF suffisamment pertinente n’a été retenue dans la base interne. La proposition formule donc des recommandations méthodologiques, des hypothèses et des questions de cadrage issues du brief client.
              </div>
            )}
            <RfpProposalDocument proposal={response.proposal} />
          </article>
        </section>
      )}
    </div>
  )
}