import { type FormEvent, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Eye, EyeOff, KeyRound, ShieldCheck, UserPlus, Users } from 'lucide-react'
import { api, errorMessage } from '../api/client.ts'
import { ErrorState } from '../components/AsyncState.tsx'
import { PageHeader } from '../components/PageHeader.tsx'
import type { UserRole } from '../types.ts'

export function UsersPage() {
  const queryClient = useQueryClient()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [role, setRole] = useState<UserRole>('CONSULTANT')
  const [showPassword, setShowPassword] = useState(false)
  const [formError, setFormError] = useState('')
  const [createdUser, setCreatedUser] = useState('')
  const users = useQuery({ queryKey: ['users'], queryFn: api.users })
  const register = useMutation({
    mutationFn: api.registerUser,
    onSuccess: async (result) => {
      setCreatedUser(result.username)
      setUsername('')
      setPassword('')
      setConfirmation('')
      setRole('CONSULTANT')
      await queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })

  const accounts = users.data ?? []
  const adminCount = accounts.filter((account) => account.role === 'ADMIN').length
  const consultantCount = accounts.length - adminCount

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError('')
    setCreatedUser('')
    if (password !== confirmation) {
      setFormError('Les deux mots de passe ne correspondent pas.')
      return
    }
    register.mutate({ username: username.trim(), password, role })
  }

  return (
    <div className="page users-page">
      <PageHeader eyebrow="Gouvernance des accès" title="Équipe et habilitations" description="Administrez les accès au patrimoine de missions avec une lecture claire des rôles et des responsabilités." action={<div className="record-count"><strong>{accounts.length}</strong><span>comptes actifs</span></div>} />

      <section className="access-overview" aria-label="Synthèse des accès">
        <div className="access-overview__lead">
          <ShieldCheck size={25} />
          <span className="eyebrow">Contrôle centralisé</span>
          <h2>Les accès restent nominatifs, traçables et gouvernés.</h2>
          <p>Chaque collaborateur se connecte avec son propre compte. Les administrateurs peuvent ouvrir de nouveaux accès ou déléguer l’administration.</p>
        </div>
        <div className="access-stat"><span>01</span><strong>{consultantCount}</strong><p>Consultants</p></div>
        <div className="access-stat"><span>02</span><strong>{adminCount}</strong><p>Administrateurs</p></div>
      </section>

      <div className="access-workspace">
        <section className="directory-section">
          <header><div><span className="eyebrow">Annuaire</span><h2>Comptes autorisés</h2></div><Users size={20} /></header>
          {users.isLoading && <div className="table-loading">Chargement des habilitations…</div>}
          {users.isError && <ErrorState message={errorMessage(users.error)} />}
          {users.data && (
            <div className="user-directory" role="table" aria-label="Utilisateurs">
              <div className="user-directory__row user-directory__row--head" role="row"><span role="columnheader">Identité</span><span role="columnheader">Rôle</span><span role="columnheader">Statut</span></div>
              {users.data.map((account) => (
                <div className="user-directory__row" role="row" key={account.id}>
                  <div role="cell" className="user-identity"><span>{account.username.slice(0, 2).toUpperCase()}</span><div><strong>{account.username}</strong><small>Compte #{String(account.id).padStart(3, '0')}</small></div></div>
                  <div role="cell"><span className={`role-badge role-badge--${account.role.toLowerCase()}`}>{account.role === 'ADMIN' ? 'Administrateur' : 'Consultant'}</span></div>
                  <div role="cell"><span className="account-status"><i /> Actif</span></div>
                </div>
              ))}
            </div>
          )}
        </section>

        <aside className="create-user-panel">
          <header><UserPlus size={21} /><div><span className="eyebrow">Nouvel accès</span><h2>Créer un compte</h2></div></header>
          <form onSubmit={submit}>
            <label>Identifiant<input minLength={3} maxLength={50} required autoComplete="off" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="prenom.nom" /></label>
            <fieldset className="role-selector"><legend>Rôle attribué</legend><div><button type="button" aria-pressed={role === 'CONSULTANT'} onClick={() => setRole('CONSULTANT')}><Users size={16} /><span>Consultant<small>Accès métier</small></span></button><button type="button" aria-pressed={role === 'ADMIN'} onClick={() => setRole('ADMIN')}><ShieldCheck size={16} /><span>Administrateur<small>Pilotage complet</small></span></button></div></fieldset>
            <label>Mot de passe<div className="password-field"><input type={showPassword ? 'text' : 'password'} minLength={8} required autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /><button type="button" onClick={() => setShowPassword((visible) => !visible)} title={showPassword ? 'Masquer le mot de passe' : 'Afficher le mot de passe'} aria-label={showPassword ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></label>
            <label>Confirmer le mot de passe<input type={showPassword ? 'text' : 'password'} minLength={8} required autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>
            {formError && <div className="form-error">{formError}</div>}
            {register.isError && <div className="form-error">{errorMessage(register.error)}</div>}
            {createdUser && <div className="form-success" role="status"><Check size={16} /> Le compte {createdUser} est désormais actif.</div>}
            <button className="button button--primary button--wide" type="submit" disabled={register.isPending}><KeyRound size={17} />{register.isPending ? 'Création…' : 'Ouvrir le compte'}</button>
          </form>
          <p className="access-note"><ShieldCheck size={14} /> Le mot de passe est haché avant stockage et n’est jamais affiché dans l’annuaire.</p>
        </aside>
      </div>
    </div>
  )
}