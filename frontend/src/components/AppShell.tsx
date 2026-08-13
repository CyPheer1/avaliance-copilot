import { useCallback, useEffect, useRef, useState } from 'react'
import { BookOpenText, ChevronDown, Command, Files, FileStack, LayoutDashboard, LogOut, Menu, Search, Users, X } from 'lucide-react'
import logoSrc from '../assets/logo.png'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/auth-context.ts'
import { CommandPalette } from './CommandPalette.tsx'
import type { CommandItem } from './CommandPalette.tsx'
import { LivingKnowledgeField } from './LivingKnowledgeField.tsx'
import { UserAvatar } from './UserAvatar.tsx'

const navigation = [
  { to: '/tableau-de-bord', label: 'Tableau de bord', section: 'Espace de travail', icon: LayoutDashboard },
  { to: '/recherche', label: 'Recherche', section: 'Espace de travail', icon: Search },
  { to: '/propositions', label: 'Propositions', section: 'Espace de travail', icon: FileStack },
  { to: '/missions', label: 'Missions', section: 'Espace de travail', icon: BookOpenText },
]

const adminNavigation = [
  { to: '/documents', label: 'Documents', section: 'Administration', icon: Files },
  { to: '/utilisateurs', label: 'Utilisateurs', section: 'Administration', icon: Users },
]

export function AppShell() {
  const { session, logout } = useAuth()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [commandOpen, setCommandOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const sidebarRef = useRef<HTMLElement>(null)
  const closeCommand = useCallback(() => setCommandOpen(false), [])
  const commandItems: CommandItem[] = session?.role === 'ADMIN' ? [...navigation, ...adminNavigation] : navigation
  const currentItem = commandItems.find((item) => location.pathname === item.to || (item.to === '/missions' && location.pathname.startsWith('/missions/')))

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === 'k') {
        event.preventDefault()
        setCommandOpen((open) => !open)
      }
    }
    document.addEventListener('keydown', handleShortcut)
    return () => document.removeEventListener('keydown', handleShortcut)
  }, [])

  useEffect(() => {    const sidebar = sidebarRef.current
    const mobileQuery = window.matchMedia('(max-width: 1023px)')

    const syncSidebarState = () => {
      if (sidebar) sidebar.inert = mobileQuery.matches && !menuOpen
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && menuOpen) {
        setMenuOpen(false)
        menuButtonRef.current?.focus()
      }
    }

    syncSidebarState()
    mobileQuery.addEventListener('change', syncSidebarState)
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      if (sidebar) sidebar.inert = false
      mobileQuery.removeEventListener('change', syncSidebarState)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [menuOpen])

  return (
    <div className="app-shell">
      <LivingKnowledgeField />
      <header className="mobile-header">
        <Brand />
        <button ref={menuButtonRef} className="icon-button" type="button" aria-controls="app-navigation" aria-expanded={menuOpen} aria-label={menuOpen ? 'Fermer la navigation' : 'Ouvrir la navigation'} title={menuOpen ? 'Fermer la navigation' : 'Ouvrir la navigation'} onClick={() => setMenuOpen((open) => !open)}>
          {menuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </header>
      <aside ref={sidebarRef} id="app-navigation" className={`sidebar ${menuOpen ? 'sidebar--open' : ''}`}>
        <div className="sidebar-brand-row">
          <button className="sidebar-workspace" type="button" aria-label="Avaliance Copilot — Espace de travail">
            <Brand />
            <span className="sidebar-workspace__meta">Espace de travail</span>
            <ChevronDown className="sidebar-workspace__chevron" size={16} strokeWidth={1.8} aria-hidden="true" />
          </button>
        </div>
        <button className="sidebar-command-search" type="button" onClick={() => setCommandOpen(true)} aria-label="Rechercher…">
          <Search size={20} strokeWidth={1.75} aria-hidden="true" />
          <span>Rechercher…</span>
          <kbd>⌘K</kbd>
        </button>
        <nav className="primary-nav" aria-label="Navigation principale">
          <span className="nav-label">Espace de travail</span>
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setMenuOpen(false)}
              className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}
            >
              <Icon size={20} strokeWidth={1.75} /><span>{label}</span>
            </NavLink>
          ))}
          {session?.role === 'ADMIN' && (
            <>
              <span className="nav-label nav-label--section">Administration</span>
              {adminNavigation.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  onClick={() => setMenuOpen(false)}
                  className={({ isActive }) => `nav-link ${isActive ? 'nav-link--active' : ''}`}
                >
                  <Icon size={20} strokeWidth={1.75} /><span>{label}</span>
                </NavLink>
              ))}
            </>
          )}
        </nav>
        <div className="sidebar-footer">
          <div className="local-status"><span className="status-dot" aria-hidden="true" /><span>Traitement local sécurisé</span></div>
          <div className="user-block">
            <UserAvatar />
            <div className="user-block__details"><strong>{session?.username}</strong><span>{session?.role === 'ADMIN' ? 'Administrateur' : 'Consultant'}</span></div>
            <button className="icon-button" type="button" onClick={logout} title="Se déconnecter" aria-label="Se déconnecter"><LogOut size={20} strokeWidth={1.75} /></button>
          </div>
        </div>
      </aside>
      {menuOpen && <button className="menu-scrim" aria-label="Fermer la navigation" onClick={() => setMenuOpen(false)} />}
      <main className="main-content">
        <header className="workspace-bar">
          <div><span>Espace Avaliance</span><strong>{currentItem?.label ?? 'Dossier de mission'}</strong></div>
          <button className="command-trigger" type="button" onClick={() => setCommandOpen(true)} aria-haspopup="dialog"><Command size={16} /><span>Accès rapide</span><kbd>Ctrl K</kbd></button>
        </header>
        <Outlet />
      </main>
      <CommandPalette open={commandOpen} items={commandItems} onClose={closeCommand} />
    </div>
  )
}

export function Brand() {
  return (
    <div className="brand" aria-label="Avaliance Copilot">
      <img src={logoSrc} alt="Avaliance Copilot logo" className="brand-logo" />
      <span className="brand-name">Avaliance <strong>Copilot</strong></span>
    </div>
  )
}