import type { ReactNode } from 'react'

interface PageHeaderProps { eyebrow: string; title: string; description: string; action?: ReactNode }

export function PageHeader({ eyebrow, title, description, action }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{description}</p></div>
      {action && <div className="page-header__action">{action}</div>}
    </header>
  )
}