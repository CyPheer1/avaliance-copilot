import { AlertTriangle, LoaderCircle } from 'lucide-react'

export function ProcessingState({ label }: { label: string }) {
  return (
    <div className="processing-state" role="status">
      <div className="processing-line"><span /></div><LoaderCircle className="spin" size={20} />
      <div><strong>{label}</strong><p>Le modèle local analyse les sources. Cette opération peut prendre jusqu’à deux minutes.</p></div>
    </div>
  )
}

export function ErrorState({ message }: { message: string }) {
  return <div className="error-state" role="alert"><AlertTriangle size={20} /><div><strong>Opération interrompue</strong><p>{message}</p></div></div>
}