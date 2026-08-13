import { type ChangeEvent, type DragEvent, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Download, FileCheck2, FileText, LoaderCircle, RefreshCw, Trash2, UploadCloud } from 'lucide-react'
import { api, errorMessage } from '../api/client.ts'
import { ErrorState } from '../components/AsyncState.tsx'
import { PageHeader } from '../components/PageHeader.tsx'
import type { DocumentStatus, SourceDocument } from '../types.ts'

const MAX_FILE_SIZE = 20 * 1024 * 1024
const ACCEPTED_EXTENSIONS = ['pdf', 'docx', 'txt']

const statusLabels: Record<DocumentStatus, string> = {
  STORED: 'Stocké',
  PROCESSING: 'Indexation',
  INDEXED: 'Indexé',
  FAILED: 'Échec',
}

export function DocumentsPage() {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [page, setPage] = useState(0)
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState('')
  const [dragActive, setDragActive] = useState(false)
  const params = new URLSearchParams({ page: String(page), size: '12', sort: 'createdAt,desc' })
  const documents = useQuery({ queryKey: ['documents', page], queryFn: () => api.documents(params) })
  const refreshDocuments = () => queryClient.invalidateQueries({ queryKey: ['documents'] })

  const upload = useMutation({
    mutationFn: api.uploadDocument,
    onSuccess: async () => {
      setFile(null)
      if (inputRef.current) inputRef.current.value = ''
      setPage(0)
      await refreshDocuments()
    },
  })
  const retry = useMutation({ mutationFn: api.retryDocument, onSuccess: refreshDocuments })
  const remove = useMutation({ mutationFn: api.deleteDocument, onSuccess: refreshDocuments })
  const download = useMutation({
    mutationFn: async (document: SourceDocument) => ({ document, blob: await api.downloadDocument(document.id) }),
    onSuccess: ({ document, blob }) => {
      const url = URL.createObjectURL(blob)
      const anchor = window.document.createElement('a')
      anchor.href = url
      anchor.download = document.filename
      anchor.click()
      URL.revokeObjectURL(url)
    },
  })

  function selectFile(candidate?: File) {
    setFileError('')
    setFile(null)
    if (!candidate) return
    const extension = candidate.name.split('.').pop()?.toLowerCase() ?? ''
    if (!ACCEPTED_EXTENSIONS.includes(extension)) {
      setFileError('Format non pris en charge. Utilisez un fichier PDF, DOCX ou TXT.')
      return
    }
    if (candidate.size > MAX_FILE_SIZE) {
      setFileError('Le fichier dépasse la limite de 20 Mo.')
      return
    }
    if (candidate.size === 0) {
      setFileError('Le fichier est vide.')
      return
    }
    setFile(candidate)
  }

  function handleInput(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0])
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragActive(false)
    selectFile(event.dataTransfer.files[0])
  }

  function deleteDocument(document: SourceDocument) {
    if (window.confirm(`Supprimer définitivement « ${document.filename} » ?`)) remove.mutate(document.id)
  }

  return (
    <div className="page documents-page">
      <PageHeader eyebrow="Corpus documentaire" title="Sources et indexation" description="Pilotez les documents d’origine utilisés par la recherche augmentée et la capitalisation interne." action={documents.data && <div className="record-count"><strong>{documents.data.totalElements}</strong><span>documents conservés</span></div>} />

      <section className="document-ingestion">
        <div className="document-ingestion__intro"><UploadCloud size={25} /><div><span className="eyebrow">Nouvelle source</span><h2>Ajouter au corpus</h2><p>PDF texte, DOCX ou TXT · 20 Mo maximum</p></div></div>
        <div
          className={`document-dropzone ${dragActive ? 'document-dropzone--active' : ''}`}
          onDragEnter={() => setDragActive(true)}
          onDragLeave={() => setDragActive(false)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
        >
          <input ref={inputRef} type="file" accept=".pdf,.docx,.txt" onChange={handleInput} aria-label="Choisir un document" />
          <FileText size={23} />
          <div>{file ? <><strong>{file.name}</strong><span>{formatSize(file.size)}</span></> : <><strong>Déposer un fichier</strong><span>ou parcourir vos documents</span></>}</div>
        </div>
        <button className="button button--primary" type="button" disabled={!file || upload.isPending} onClick={() => file && upload.mutate(file)}>{upload.isPending ? <LoaderCircle className="spin" size={17} /> : <UploadCloud size={17} />}{upload.isPending ? 'Extraction et indexation…' : 'Importer la source'}</button>
      </section>
      {fileError && <div className="form-error document-feedback">{fileError}</div>}
      {upload.isError && <ErrorState message={errorMessage(upload.error)} />}
      {remove.isError && <ErrorState message={errorMessage(remove.error)} />}
      {retry.isError && <ErrorState message={errorMessage(retry.error)} />}
      {download.isError && <ErrorState message={errorMessage(download.error)} />}

      <section className="document-directory">
        <header><div><span className="eyebrow">Registre des sources</span><h2>Documents disponibles</h2></div><FileCheck2 size={21} /></header>
        {documents.isLoading && <div className="table-loading">Chargement des documents…</div>}
        {documents.isError && <ErrorState message={errorMessage(documents.error)} />}
        {documents.data?.empty && <div className="empty-table"><FileText size={22} /><p>Aucun document n’a encore été versé au corpus.</p></div>}
        {documents.data && !documents.data.empty && (
          <>
            <div className="document-table" role="table" aria-label="Documents du corpus">
              <div className="document-row document-row--head" role="row"><span role="columnheader">Document</span><span role="columnheader">État</span><span role="columnheader">Index</span><span role="columnheader">Ajout</span><span role="columnheader">Actions</span></div>
              {documents.data.content.map((document) => (
                <div className="document-row" role="row" key={document.id}>
                  <div role="cell" className="document-identity"><span className="document-file-icon"><FileText size={18} /></span><div><strong>{document.filename}</strong><small>{formatSize(document.sizeBytes)} · {document.uploadedBy}</small>{document.errorMessage && <p title={document.errorMessage}>{document.errorMessage}</p>}</div></div>
                  <div role="cell"><span className={`document-status document-status--${document.status.toLowerCase()}`}>{document.status === 'PROCESSING' && <LoaderCircle className="spin" size={12} />}<i />{statusLabels[document.status]}</span></div>
                  <div role="cell" className="document-index"><strong>{document.chunkCount ?? '—'}</strong><span>segments</span>{document.pageCount !== null && <small>{document.pageCount} pages</small>}</div>
                  <div role="cell" className="document-date"><strong>{formatDate(document.createdAt)}</strong><span>{document.indexedAt ? `Indexé ${formatDate(document.indexedAt)}` : `DOC-${String(document.id).padStart(4, '0')}`}</span></div>
                  <div role="cell" className="document-actions-row">
                    {document.status === 'FAILED' && <button className="icon-button" type="button" onClick={() => retry.mutate(document.id)} disabled={retry.isPending} title="Relancer l’indexation" aria-label={`Relancer l’indexation de ${document.filename}`}><RefreshCw size={16} /></button>}
                    <button className="icon-button" type="button" onClick={() => download.mutate(document)} disabled={download.isPending} title="Télécharger l’original" aria-label={`Télécharger ${document.filename}`}><Download size={16} /></button>
                    <button className="icon-button icon-button--danger" type="button" onClick={() => deleteDocument(document)} disabled={remove.isPending || document.status === 'PROCESSING'} title="Supprimer" aria-label={`Supprimer ${document.filename}`}><Trash2 size={16} /></button>
                  </div>
                </div>
              ))}
            </div>
            <footer className="pagination"><span>Page {documents.data.number + 1} sur {documents.data.totalPages}</span><div><button className="icon-button" type="button" disabled={documents.data.first} onClick={() => setPage((value) => value - 1)} title="Page précédente" aria-label="Page précédente"><ArrowLeft size={18} /></button><button className="icon-button" type="button" disabled={documents.data.last} onClick={() => setPage((value) => value + 1)} title="Page suivante" aria-label="Page suivante"><ArrowRight size={18} /></button></div></footer>
          </>
        )}
      </section>
    </div>
  )
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} o`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value))
}