import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, MouseEvent } from 'react'
import { ArrowRight, Eye, EyeOff, KeyRound, LockKeyhole, User } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import type { Variants } from 'motion/react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import logoSrc from '../assets/logo.png'
import { errorMessage } from '../api/client.ts'
import { useAuth } from '../auth/auth-context.ts'
import { EvidenceGraph } from './login/EvidenceGraph.tsx'

const editorialSteps = [
  {
    index: '01',
    label: 'Rechercher',
    description: 'Recherche hybride dans le patrimoine',
    accentClass: 'is-violet',
  },
  {
    index: '02',
    label: 'Comparer',
    description: 'Références et missions comparables',
    accentClass: 'is-medium',
  },
  {
    index: '03',
    label: 'Produire',
    description: 'Structures de proposition prêtes',
    accentClass: 'is-lime',
  },
]

const easing = [0.16, 1, 0.3, 1] as const

export function LoginPage() {
  const { session, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const reducedMotion = useReducedMotion()
  const cardRef = useRef<HTMLDivElement>(null)
  const glowFrameRef = useRef<number | null>(null)
  const pointerRef = useRef({ x: 200, y: 200 })
  const submissionInProgressRef = useRef(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [activeStep, setActiveStep] = useState(0)
  const [capsLockActive, setCapsLockActive] = useState(false)

  useEffect(() => {
    if (reducedMotion) {
      return undefined
    }

    const timer = window.setInterval(() => {
      setActiveStep((current) => (current + 1) % editorialSteps.length)
    }, 3000)

    return () => window.clearInterval(timer)
  }, [reducedMotion])

  useEffect(() => () => {
    if (glowFrameRef.current !== null) {
      window.cancelAnimationFrame(glowFrameRef.current)
    }
  }, [])

  const cardVariants = useMemo(() => ({
    hidden: { opacity: 0, y: 14, scale: 0.985 },
    show: {
      opacity: 1,
      y: 0,
      scale: 1,
      transition: { duration: 0.42, delay: 0.2, ease: easing },
    },
  } satisfies Variants), [])

  const stripeVariants = useMemo(() => ({
    hidden: { scaleX: 0 },
    show: {
      scaleX: 1,
      transition: { duration: 0.52, delay: 0.34, ease: easing },
    },
  } satisfies Variants), [])

  const formVariants = useMemo(() => ({
    hidden: {},
    show: {
      transition: {
        delayChildren: 0.42,
        staggerChildren: 0.055,
      },
    },
  } satisfies Variants), [])

  const entryVariants = useMemo(() => ({
    hidden: { opacity: 0, y: 8 },
    show: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.3, ease: easing },
    },
  } satisfies Variants), [])

  const syncCardGlow = () => {
    glowFrameRef.current = null
    if (!cardRef.current) {
      return
    }

    cardRef.current.style.setProperty('--mx', `${pointerRef.current.x}px`)
    cardRef.current.style.setProperty('--my', `${pointerRef.current.y}px`)
  }

  const handleCardPointerMove = (event: MouseEvent<HTMLDivElement>) => {
    if (reducedMotion || !cardRef.current) {
      return
    }

    const rect = cardRef.current.getBoundingClientRect()
    pointerRef.current = {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    }

    if (glowFrameRef.current === null) {
      glowFrameRef.current = window.requestAnimationFrame(syncCardGlow)
    }
  }

  const handleCardPointerLeave = () => {
    if (!cardRef.current) {
      return
    }

    pointerRef.current = {
      x: cardRef.current.clientWidth * 0.5,
      y: cardRef.current.clientHeight * 0.28,
    }

    if (!reducedMotion && glowFrameRef.current === null) {
      glowFrameRef.current = window.requestAnimationFrame(syncCardGlow)
    }
  }

  const handlePasswordKeyState = (capsLock: boolean) => {
    setCapsLockActive(capsLock)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (submissionInProgressRef.current) return

    submissionInProgressRef.current = true
    setError('')
    setPending(true)
    try {
      await login(username, password)
      const destination = (location.state as { from?: string } | null)?.from ?? '/tableau-de-bord'
      navigate(destination, { replace: true })
    } catch (nextError) {
      // Keep the error visible in the login form even if a fetch, CORS, JSON,
      // storage, or AuthContext failure occurs after the request is started.
      setError(errorMessage(nextError) || 'Une erreur de connexion est survenue. Réessayez.')
    } finally {
      submissionInProgressRef.current = false
      setPending(false)
    }
  }

  if (session) return <Navigate to="/tableau-de-bord" replace />

  return (
    <main className="login-page">
      <section className="login-context">
        <div className="login-context__ambient" aria-hidden="true">
          <div className="login-context__mesh login-context__mesh--violet" />
          <div className="login-context__mesh login-context__mesh--medium" />
          <div className="login-context__mesh login-context__mesh--lime" />
          <div className="login-context__mesh login-context__mesh--violet-lower" />
          <div className="login-context__mesh login-context__mesh--medium-lower" />
          <div className="login-context__grid" />
        </div>

        <EvidenceGraph className="login-context__graph" reducedMotion={!!reducedMotion} />

        <div className="login-context__status" aria-hidden="true">
          <span className="login-context__status-dot" aria-hidden="true" />
          <span>Traitement local sécurisé</span>
        </div>

        <div className="login-context__content">
          <div className="login-context__top">
            <div className="login-context__brand-wrap">
              <motion.div
                className="login-context__brand-orbit"
                initial={reducedMotion ? false : { opacity: 0, scale: 0.88 }}
                animate={reducedMotion ? { opacity: 1, scale: 1 } : { opacity: 1, scale: 1 }}
                transition={{ duration: 0.62, ease: easing }}
              >
                <div className="login-context__brand-rings" aria-hidden="true">
                  <span className="login-context__brand-ring login-context__brand-ring--inner" />
                  <span className="login-context__brand-ring login-context__brand-ring--outer" />
                </div>
                <div className="login-context__brand-halo" aria-hidden="true" />
                <motion.div
                  className="login-context__brand-logo"
                  initial={reducedMotion ? false : { opacity: 0, scale: 0.88 }}
                  animate={reducedMotion ? { opacity: 1, scale: 1 } : { opacity: 1, scale: 1, y: [0, -4, 0] }}
                  transition={reducedMotion ? { duration: 0.62, ease: easing } : { duration: 0.62, ease: easing, y: { duration: 7, repeat: Infinity, repeatType: 'mirror', ease: 'easeInOut' } }}
                >
                  <img src={logoSrc} alt="Avaliance Copilot" className="login-context__brand-image" />
                </motion.div>
                <motion.span
                  className="login-context__brand-name"
                  initial={reducedMotion ? false : { opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.32, delay: 0.12, ease: easing }}
                >
                  Avaliance Copilot
                </motion.span>
              </motion.div>
            </div>
          </div>

          <div className="login-context__spacer" aria-hidden="true" />

          <div className="login-context__bottom">
            <div className="login-context__statement">
              <span className="eyebrow">PATRIMOINE DE MISSIONS</span>
              <h1 aria-label="Produire avec les preuves en regard.">
                <motion.span className="login-title-line" initial={reducedMotion ? false : { opacity: 0, y: '100%' }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.52, ease: easing }}>Produire avec les preuves</motion.span>
                <motion.span className="login-title-line" initial={reducedMotion ? false : { opacity: 0, y: '100%' }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.52, delay: 0.09, ease: easing }}>en regard.</motion.span>
              </h1>
              <p>Recherche hybride, références comparables et structures de proposition, dans un espace confidentiel.</p>

              <div className="login-steps" aria-label="Explication du produit">
                {editorialSteps.map((step, index) => {
                  const active = index === activeStep

                  return (
                    <motion.div
                      key={step.index}
                      className={`login-step ${step.accentClass} ${active ? 'is-active' : ''}`}
                      initial={reducedMotion ? false : { opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.32, delay: 0.22 + index * 0.06, ease: easing }}
                    >
                      <span className="login-step__dot" aria-hidden="true" />
                      <span className="login-step__index">{step.index}</span>
                      <span className="login-step__label">{step.label}</span>
                      <span className="login-step__desc">{step.description}</span>
                    </motion.div>
                  )
                })}
              </div>
            </div>

            <div className="login-context__footer" aria-hidden="true">
              <div className="login-context__footer-track">
                <div className="login-context__footer-copy">
                  <span>CLOUD · DATA & IA · CYBERSÉCURITÉ · TÉLÉCOM · ÉNERGIE</span>
                </div>
                <div className="login-context__footer-copy">
                  <span>CLOUD · DATA & IA · CYBERSÉCURITÉ · TÉLÉCOM · ÉNERGIE</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section className="login-panel">
        <motion.div
          ref={cardRef}
          className={`login-panel__card${error ? ' is-error' : ''}`}
          variants={cardVariants}
          initial={reducedMotion ? false : 'hidden'}
          animate="show"
          onMouseMove={handleCardPointerMove}
          onMouseLeave={handleCardPointerLeave}
        >
          <span className="login-panel__scene login-panel__scene--dots" aria-hidden="true" />
          <span className="login-panel__scene login-panel__scene--halo" aria-hidden="true" />
          <motion.span className="login-panel__card-accent" variants={stripeVariants} aria-hidden="true" />
          <motion.form className="login-form" onSubmit={submit} variants={formVariants} initial={false} animate="show">
            <motion.div className="login-form__identity" variants={entryVariants}>
              <img src={logoSrc} alt="" className="login-form__identity-logo" />
              <span>Avaliance Copilot</span>
            </motion.div>

            <motion.span className="eyebrow login-form__eyebrow" variants={entryVariants}>
              <LockKeyhole size={12} aria-hidden="true" />
              <span>ACCÈS RÉSERVÉ</span>
            </motion.span>

            <motion.h2 variants={entryVariants}>Ouvrir votre espace</motion.h2>
            <motion.p variants={entryVariants}>Utilisez vos identifiants Avaliance Copilot.</motion.p>

            <motion.label className={`login-field${username ? ' is-filled' : ''}`} variants={entryVariants}>
              <span className="login-field__control">
                <User size={16} className="login-field__icon" aria-hidden="true" />
                <input autoFocus autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required />
                <span className="login-field__floating">Identifiant</span>
              </span>
            </motion.label>

            <motion.label className={`login-field${password ? ' is-filled' : ''}`} variants={entryVariants}>
              <span className="login-field__control login-password">
                <KeyRound size={16} className="login-field__icon" aria-hidden="true" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  onKeyDown={(event) => handlePasswordKeyState(event.getModifierState('CapsLock'))}
                  onKeyUp={(event) => handlePasswordKeyState(event.getModifierState('CapsLock'))}
                  onBlur={() => handlePasswordKeyState(false)}
                  required
                />
                <span className="login-field__floating">Mot de passe</span>
                <button type="button" onClick={() => setShowPassword((current) => !current)} aria-label={showPassword ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}>
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </span>
              <span className={`login-field__caps${capsLockActive ? ' is-visible' : ''}`}>Verr. Maj active</span>
            </motion.label>

            <motion.div className="login-form__error-slot" aria-live="polite" variants={entryVariants}>
              {error ? <motion.div className="form-error login-form__error" role="alert" initial={reducedMotion ? false : { opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.18, ease: easing }}>{error}</motion.div> : null}
            </motion.div>

            <motion.button className="login-submit" disabled={pending} type="submit" variants={entryVariants} aria-busy={pending}>
              {pending ? <span className="login-submit__spinner" aria-hidden="true" /> : <span>Se connecter</span>}
              {!pending ? <ArrowRight size={16} className="login-submit__arrow" aria-hidden="true" /> : null}
            </motion.button>

            <motion.p className="login-form__hint" variants={entryVariants}>Entrée pour valider</motion.p>

            <motion.div className="login-form__footer" variants={entryVariants}>
              <small>Les traitements documentaires et le modèle de génération restent sur l’infrastructure locale.</small>
              <div className="login-form__meta">
                <span className="login-form__meta-item">
                  <span className="login-form__meta-dot" aria-hidden="true" />
                  <span>Infrastructure locale</span>
                </span>
              </div>
            </motion.div>
          </motion.form>
        </motion.div>
      </section>
    </main>
  )
}