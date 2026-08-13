import { useCallback, useDeferredValue, useEffect, useRef, useState } from 'react'
import { ArrowRight, Search, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

export interface CommandItem {
  to: string
  label: string
  section: string
  icon: LucideIcon
}

export function CommandPalette({ open, items, onClose }: { open: boolean; items: CommandItem[]; onClose: () => void }) {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query.trim().toLocaleLowerCase('fr-FR'))
  const filteredItems = items.filter((item) => `${item.label} ${item.section}`.toLocaleLowerCase('fr-FR').includes(deferredQuery))
  const close = useCallback(() => {
    setQuery('')
    onClose()
  }, [onClose])

  useEffect(() => {
    if (!open) return undefined
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.requestAnimationFrame(() => inputRef.current?.focus())

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [close, open])

  if (!open) return null

  const select = (to: string) => {
    navigate(to)
    close()
  }

  return (
    <div className="command-overlay" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && close()}>
      <section className="command-palette" role="dialog" aria-modal="true" aria-labelledby="command-title">
        <header className="command-palette__header">
          <Search size={18} aria-hidden="true" />
          <label className="sr-only" htmlFor="command-search" id="command-title">Accès rapide</label>
          <input ref={inputRef} id="command-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Rechercher une destination…" />
          <button className="icon-button" type="button" onClick={close} aria-label="Fermer l’accès rapide" title="Fermer"><X size={17} /></button>
        </header>
        <div className="command-palette__body">
          {filteredItems.length > 0 ? filteredItems.map(({ to, label, section, icon: Icon }) => (
            <button key={to} className="command-item" type="button" onClick={() => select(to)}>
              <span className="command-item__icon"><Icon size={18} strokeWidth={1.8} /></span>
              <span><strong>{label}</strong><small>{section}</small></span>
              <ArrowRight size={16} aria-hidden="true" />
            </button>
          )) : <p className="command-empty">Aucune destination ne correspond à votre recherche.</p>}
        </div>
        <footer className="command-palette__footer"><span><kbd>Entrée</kbd> ouvrir</span><span><kbd>Échap</kbd> fermer</span></footer>
      </section>
    </div>
  )
}