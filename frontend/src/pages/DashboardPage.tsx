import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import NumberFlow from '@number-flow/react'
import { ArrowRight, FileStack, Search, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion, useInView, useReducedMotion } from 'motion/react'
import { api, errorMessage } from '../api/client.ts'
import { ErrorState } from '../components/AsyncState.tsx'
import { DashboardMotionProvider } from '../components/motion/DashboardMotionProvider.tsx'
import { useDashboardMotion } from '../components/motion/useDashboardMotion.ts'
import { Reveal } from '../components/motion/Reveal.tsx'
import { compactContainerVariants, containerVariants, itemVariants } from '../components/motion/variants.ts'
import type { DashboardBreakdown, DashboardSummary } from '../types.ts'

const fmtNum = new Intl.NumberFormat('fr-FR')
const fmtCompact = new Intl.NumberFormat('fr-FR', { notation: 'compact', maximumFractionDigits: 1 })
const fmtDate = new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
const fmtDay = (iso: string) => new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: 'short' }).format(new Date(`${iso}T12:00:00Z`))

type KpiVariant = 'missions' | 'activity' | 'target' | 'latency'

export function DashboardPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['dashboard', 30],
    queryFn: () => api.dashboard(30),
    refetchInterval: 60_000,
  })
  const reducedMotion = useReducedMotion()

  return (
    <DashboardMotionProvider value={{ reducedMotion: !!reducedMotion }}>
      <AnimatePresence mode="wait" initial={false}>
        {isLoading ? (
          <motion.div
            key="dashboard-loading"
            className="page db-page"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
          >
            <DashboardSkeleton />
          </motion.div>
        ) : isError ? (
          <motion.div
            key="dashboard-error"
            className="page db-page"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
          >
            <ErrorState message={errorMessage(error)} />
          </motion.div>
        ) : data ? (
          <motion.div
            key="dashboard-content"
            className="page db-page"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
          >
            <DashboardContent data={data} />
          </motion.div>
        ) : null}
      </AnimatePresence>
    </DashboardMotionProvider>
  )
}

function DashboardContent({ data }: { data: DashboardSummary }) {
  return (
    <>
      <Reveal delay={0}><DashHeader generatedAt={data.generatedAt} /></Reveal>
      <Reveal delay={90} className="db-kpi-row-reveal"><KpiRow data={data} /></Reveal>
      <div className="db-main-row">
        <Reveal delay={260}><ActivityPanel data={data} /></Reveal>
        <Reveal delay={360}><UsagePanel data={data} /></Reveal>
      </div>
      <div className="db-dist-row-outer-grid">
        <Reveal delay={420}><DistPanel title="Missions par secteur" meta={`${data.missionsBySector.length} segments`} items={data.missionsBySector} /></Reveal>
        <Reveal delay={460}><DistPanel title="Nature des interventions" meta={`${data.missionsByType.length} types`} items={data.missionsByType} /></Reveal>
      </div>
      <Reveal delay={560}><QuickActions /></Reveal>
    </>
  )
}

function DashHeader({ generatedAt }: { generatedAt: string }) {
  return (
    <header className="db-header">
      <div>
        <span className="db-eyebrow">Pilotage</span>
        <h1 className="db-title">Vue d'ensemble</h1>
      </div>
      <div className="db-freshness">
        <span className="db-freshness__dot" aria-hidden="true" />
        <span>Actualisé {fmtDate.format(new Date(generatedAt))}</span>
      </div>
    </header>
  )
}

function KpiRow({ data }: { data: DashboardSummary }) {
  return (
    <motion.div className="db-kpi-row" role="region" aria-label="Indicateurs clés" variants={containerVariants} initial="hidden" animate="show">
      <KpiCard label="Missions capitalisées" value={data.missionTotal} context={`${data.missionsBySector.length} secteurs`} icon="missions" decimals={0} />
      <KpiCard label="Activités (30 j)" value={data.activity.total} context={`${data.activity.searches} recherches`} icon="activity" decimals={0} />
      <KpiCard label="Taux de réussite" value={data.activity.successRate} context={`${data.activity.errors} erreur${data.activity.errors === 1 ? '' : 's'}`} icon="target" decimals={1} suffix=" %" />
      <KpiCard label="Temps de réponse" value={data.activity.averageDurationMs} context="Toutes opérations" icon="latency" isDuration />
    </motion.div>
  )
}

function KpiCard({
  label,
  value,
  suffix = '',
  context,
  decimals = 0,
  isDuration = false,
  icon,
}: {
  label: string
  value: number
  suffix?: string
  context: string
  decimals?: number
  isDuration?: boolean
  icon: KpiVariant
}) {
  const ref = useRef<HTMLDivElement>(null)
  const { reducedMotion } = useDashboardMotion()
  const inView = useInView(ref, { once: true, amount: 0.2 })

  const display = isDuration
    ? getDurationParts(value)
    : {
      value,
      numeric: decimals > 0
        ? value.toLocaleString('fr-FR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
        : fmtNum.format(Math.round(value)),
      unit: suffix,
      decimals,
    }

  const animateNumbers = !reducedMotion && inView
  const numberValue = isDuration ? display.value : value
  const fractionDigits = isDuration ? display.decimals : decimals
  const unitLabel = (isDuration ? display.unit : suffix).trim()

  return (
    <motion.article
      className="db-kpi"
      variants={itemVariants}
      whileHover={reducedMotion ? undefined : { y: -1 }}
      transition={{ duration: 0.13, ease: [0.16, 1, 0.3, 1] }}
      data-kpi-icon={icon}
    >
      <div ref={ref} className="db-kpi__content">
        <span className="db-kpi__label">{label}</span>
        <div className="db-kpi__metric">
          <div className="db-kpi__value-row">
            <strong className="db-kpi__value">
              <NumberFlow
                value={numberValue}
                locales="fr-FR"
                animated={animateNumbers}
                willChange={animateNumbers}
                format={{
                  minimumFractionDigits: fractionDigits,
                  maximumFractionDigits: fractionDigits,
                }}
                transformTiming={{ duration: 520, easing: 'cubic-bezier(0.16,1,0.3,1)' }}
              />
            </strong>
            {unitLabel ? <span className="db-kpi__unit">{unitLabel}</span> : null}
          </div>
          <span className="db-kpi__ctx" title={context}>{context}</span>
        </div>
      </div>
    </motion.article>
  )
}

function ActivityPanel({ data }: { data: DashboardSummary }) {
  const ref = useRef<HTMLDivElement>(null)
  const { reducedMotion } = useDashboardMotion()
  const inView = useInView(ref, { once: true, amount: 0.2 })
  const [hovered, setHovered] = useState<number | null>(null)
  const [tooltip, setTooltip] = useState<{ x: number; y: number; day: string; total: number } | null>(null)
  const pathRef = useRef<SVGPathElement>(null)

  const W = 900
  const H = 200
  const rawMax = Math.max(1, ...data.dailyActivity.map((d) => d.total))
  const yMax = rawMax * 1.15
  const pts = data.dailyActivity.map((d, i) => {
    const x = data.dailyActivity.length === 1 ? 0 : (i * W) / (data.dailyActivity.length - 1)
    const y = H - (d.total / yMax) * H
    return { ...d, x, y }
  })

  const linePath = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const areaPath = `${linePath} L${(pts.at(-1)?.x ?? W).toFixed(1)},${H} L0,${H} Z`
  const yLabels = [0, Math.round(rawMax / 2), rawMax]
  const xLabels = [0, Math.floor((pts.length - 1) / 3), Math.floor((2 * (pts.length - 1)) / 3), pts.length - 1]
  const animateChart = !reducedMotion && inView
  const activitySummary = pts.length > 0
    ? `Activité quotidienne sur ${data.periodDays} jours. Maximum ${fmtNum.format(rawMax)} opérations. ${pts.map((point) => `${fmtDay(point.day)} : ${fmtNum.format(point.total)}`).join(', ')}.`
    : `Aucune activité enregistrée sur les ${data.periodDays} derniers jours.`

  useEffect(() => {
    const el = pathRef.current
    if (!el) {
      return
    }

    if (!animateChart) {
      el.style.strokeDasharray = 'none'
      el.style.strokeDashoffset = '0'
      return
    }

    const length = el.getTotalLength()
    el.style.strokeDasharray = `${length}`
    el.style.strokeDashoffset = `${length}`
    const frame = requestAnimationFrame(() => {
      el.style.transition = 'stroke-dashoffset 620ms ease-out'
      el.style.strokeDashoffset = '0'
    })

    return () => cancelAnimationFrame(frame)
  }, [animateChart, linePath])

  return (
    <div ref={ref} className="db-panel db-chart-panel">
      <header className="db-panel__head">
        <span className="db-panel__title">Activité quotidienne</span>
        <span className="db-panel__meta">{data.periodDays} jours</span>
      </header>
      <div className="db-chart-wrap" onPointerLeave={() => { setHovered(null); setTooltip(null) }}>
        <div className="db-chart-y">
          {[...yLabels].reverse().map((v) => <span key={v}>{fmtCompact.format(v)}</span>)}
        </div>
        <div className="db-chart-area">
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="db-chart-svg" role="img" aria-label={activitySummary}>
            <defs>
              <linearGradient id="dbChartFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="rgba(18, 50, 78, 0.10)" />
                <stop offset="100%" stopColor="rgba(18, 50, 78, 0)" />
              </linearGradient>
            </defs>
            {[0, H / 2, H].map((y) => <line key={y} x1={0} y1={y} x2={W} y2={y} className="db-chart-grid" />)}
            <motion.path
              d={areaPath}
              className="db-chart-fill"
              initial={{ opacity: 0 }}
              animate={{ opacity: animateChart ? 1 : 1 }}
              transition={{ duration: 0.4, delay: 0.5, ease: 'easeOut' }}
            />
            <motion.path
              ref={pathRef}
              d={linePath}
              className="db-chart-line"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.62, delay: 0.3, ease: 'easeOut' }}
            />
            {pts.map((p, i) => (
              <g key={p.day}>
                <rect
                  x={i === 0 ? 0 : (pts[i - 1].x + p.x) / 2}
                  width={p.x - (i === 0 ? 0 : (pts[i - 1].x + p.x) / 2) + (pts[i + 1] ? (pts[i + 1].x + p.x) / 2 - p.x : 0)}
                  y={0}
                  height={H}
                  fill="transparent"
                  onPointerEnter={() => { setHovered(i); setTooltip({ x: p.x, y: p.y, day: p.day, total: p.total }) }}
                  style={{ cursor: 'crosshair' }}
                />
                {(i === pts.length - 1 || hovered === i) && (
                  <motion.circle
                    cx={p.x}
                    cy={p.y}
                    r={hovered === i ? 4 : 3}
                    className="db-chart-dot"
                    initial={{ opacity: 0, scale: 0.6 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.62, delay: 0.62, ease: [0.16, 1, 0.3, 1] }}
                  />
                )}
              </g>
            ))}
          </svg>
          <AnimatePresence>
            {tooltip && (
              <motion.div
                className="db-tooltip"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                transition={{ duration: 0.13, ease: [0.16, 1, 0.3, 1] }}
                style={{ left: `${Math.min((tooltip.x / W) * 100, 80)}%`, top: `${Math.max(0, (tooltip.y / H) * 100 - 16)}%` }}
              >
                <span>{fmtDay(tooltip.day)}</span>
                <strong>{fmtNum.format(tooltip.total)} op.</strong>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
      <div className="db-chart-x">
        {xLabels.map((i) => pts[i] && <span key={pts[i].day}>{fmtDay(pts[i].day)}</span>)}
      </div>
    </div>
  )
}

function UsagePanel({ data }: { data: DashboardSummary }) {
  const ref = useRef<HTMLDivElement>(null)
  const { reducedMotion } = useDashboardMotion()
  const inView = useInView(ref, { once: true, amount: 0.2 })
  const rows = [
    { label: 'Recherche', value: data.activity.searches },
    { label: 'Similarité', value: data.activity.similarities },
    { label: 'Proposition', value: data.activity.rfpGenerations },
  ]
  const max = Math.max(1, ...rows.map((row) => row.value))
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)

  return (
    <div ref={ref} className="db-panel db-usage-panel">
      <header className="db-panel__head">
        <span className="db-panel__title">Usage des capacités</span>
        <span className="db-panel__meta">{fmtNum.format(data.activity.total)} op.</span>
      </header>
      <motion.div className="db-usage-list" variants={containerVariants} initial="hidden" animate={inView ? 'show' : 'hidden'}>
        {rows.map((row, index) => (
          <motion.div
            key={row.label}
            className={`db-usage-row${hoveredIndex !== null && hoveredIndex !== index ? ' is-dimmed' : ''}${hoveredIndex === index ? ' is-active' : ''}`}
            variants={itemVariants}
            initial="hidden"
            animate={inView ? 'show' : 'hidden'}
            onPointerEnter={() => setHoveredIndex(index)}
            onPointerLeave={() => setHoveredIndex(null)}
          >
            <span className="db-usage-row__label">{row.label}</span>
            <div className="db-usage-row__track">
              <motion.span
                className="db-usage-row__fill"
                initial={{ scaleX: 0 }}
                animate={{ scaleX: reducedMotion ? row.value / max : inView ? row.value / max : 0 }}
                transition={{ duration: reducedMotion ? 0 : 0.5, delay: reducedMotion ? 0 : 0.36 + index * 0.06, ease: [0.16, 1, 0.3, 1] }}
                style={{ transformOrigin: 'left' }}
              />
              <motion.span
                className="db-usage-row__dot"
                initial={{ opacity: 0, scale: 0.6 }}
                animate={{ opacity: inView ? 1 : 0, scale: inView ? 1 : 0.6 }}
                transition={{ duration: 0.13, delay: reducedMotion ? 0 : 0.36 + index * 0.06 + 0.45, ease: [0.16, 1, 0.3, 1] }}
                style={{ left: `${Math.max((row.value / max) * 100, 3)}%` }}
              />
            </div>
            <div className="db-usage-row__value">
              <NumberFlow
                value={row.value}
                locales="fr-FR"
                animated={!reducedMotion}
                format={{ maximumFractionDigits: 0 }}
                transformTiming={{ duration: 520, easing: 'cubic-bezier(0.16,1,0.3,1)' }}
              />
            </div>
          </motion.div>
        ))}
      </motion.div>
    </div>
  )
}

function DistPanel({ title, meta, items }: { title: string; meta: string; items: DashboardBreakdown[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const { reducedMotion } = useDashboardMotion()
  const inView = useInView(ref, { once: true, amount: 0.2 })
  const visible = useMemo(() => [...items].sort((a, b) => b.total - a.total).slice(0, 5), [items])
  const totals = visible.map((item) => item.total)
  const max = Math.max(1, ...totals)
  const allEqual = visible.length > 0 && totals.every((total) => total === totals[0])
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
  const panelMeta = allEqual ? `${meta} · répartition uniforme` : meta

  return (
    <div ref={ref} className="db-panel db-dist-panel">
      <header className="db-panel__head">
        <span className="db-panel__title">{title}</span>
        <span className="db-panel__meta">{panelMeta}</span>
      </header>
      {visible.length === 0 ? (
        <p className="db-empty">Aucune donnée exploitable pour cette vue.</p>
      ) : (
        <motion.div className="db-dist-list" variants={compactContainerVariants} initial="hidden" animate={inView ? 'show' : 'hidden'}>
          {visible.map((item, index) => {
            const ratio = allEqual ? 1 : item.total / max

            return (
              <motion.div
                key={item.label}
                className={`db-dist-row${hoveredIndex !== null && hoveredIndex !== index ? ' is-dimmed' : ''}${hoveredIndex === index ? ' is-active' : ''}`}
                variants={itemVariants}
                initial="hidden"
                animate={inView ? 'show' : 'hidden'}
                onPointerEnter={() => setHoveredIndex(index)}
                onPointerLeave={() => setHoveredIndex(null)}
              >
                <span className="db-dist-bar-bg" aria-hidden="true">
                  <motion.span
                    className="db-dist-bar-fill"
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: reducedMotion ? ratio : inView ? ratio : 0 }}
                    transition={{ duration: reducedMotion ? 0 : 0.5, delay: reducedMotion ? 0 : 0.04 + index * 0.04, ease: [0.16, 1, 0.3, 1] }}
                    style={{ transformOrigin: 'left' }}
                  />
                </span>
                <div className="db-dist-row__top">
                  <span className="db-dist-row__label" title={item.label}>{item.label}</span>
                  <span className="db-dist-row__val">{fmtNum.format(item.total)}</span>
                </div>
              </motion.div>
            )
          })}
        </motion.div>
      )}
    </div>
  )
}

function QuickActions() {
  return (
    <motion.nav className="db-actions" aria-label="Actions rapides" variants={containerVariants} initial="hidden" animate="show">
      <ActionLink to="/recherche" icon={Search} label="Lancer une recherche" />
      <ActionLink to="/propositions" icon={FileStack} label="Créer une proposition" />
      <ActionLink to="/missions" icon={Sparkles} label="Explorer les missions" />
    </motion.nav>
  )
}

function ActionLink({
  to,
  icon: Icon,
  label,
}: {
  to: string
  icon: typeof Search
  label: string
}) {
  return (
    <motion.div className="db-actions__item" variants={itemVariants}>
      <Link className="db-action" to={to}>
        <span className="db-action__shine" aria-hidden="true" />
        <Icon size={14} className="db-action__icon" />
        <span>{label}</span>
        <ArrowRight size={13} className="db-action__arrow" />
      </Link>
    </motion.div>
  )
}

function DashboardSkeleton() {
  return (
    <>
      <div className="db-header db-skeleton-shell">
        <div>
          <span className="db-skeleton-line db-skeleton-line--eyebrow" />
          <span className="db-skeleton-line db-skeleton-line--title" />
        </div>
        <span className="db-skeleton-pill" />
      </div>
      <div className="db-kpi-row">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="db-kpi db-skeleton-card">
            <span className="db-skeleton-line db-skeleton-line--label" />
            <span className="db-skeleton-line db-skeleton-line--value" />
            <span className="db-skeleton-line db-skeleton-line--ctx" />
          </div>
        ))}
      </div>
      <div className="db-main-row">
        <div className="db-panel db-chart-panel db-skeleton-panel">
          <div className="db-panel__head"><span className="db-skeleton-line db-skeleton-line--panel" /><span className="db-skeleton-line db-skeleton-line--meta" /></div>
          <div className="db-chart-skeleton" />
          <div className="db-chart-x"><span className="db-skeleton-line db-skeleton-line--tick" /><span className="db-skeleton-line db-skeleton-line--tick" /><span className="db-skeleton-line db-skeleton-line--tick" /><span className="db-skeleton-line db-skeleton-line--tick" /></div>
        </div>
        <div className="db-panel db-usage-panel db-skeleton-panel">
          <div className="db-panel__head"><span className="db-skeleton-line db-skeleton-line--panel" /><span className="db-skeleton-line db-skeleton-line--meta" /></div>
          <div className="db-usage-list">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="db-usage-row db-skeleton-row">
                <span className="db-skeleton-line db-skeleton-line--label-sm" />
                <div className="db-usage-row__track"><span className="db-skeleton-bar" /></div>
                <span className="db-skeleton-line db-skeleton-line--value-sm" />
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="db-dist-row-outer-grid">
        {Array.from({ length: 2 }).map((_, panelIndex) => (
          <div key={panelIndex} className="db-panel db-dist-panel db-skeleton-panel">
            <div className="db-panel__head"><span className="db-skeleton-line db-skeleton-line--panel" /><span className="db-skeleton-line db-skeleton-line--meta" /></div>
            <div className="db-dist-list">
              {Array.from({ length: 5 }).map((_, rowIndex) => (
                <div key={rowIndex} className="db-dist-row db-skeleton-row">
                  <div className="db-dist-bar-bg"><span className="db-skeleton-bar" /></div>
                  <div className="db-dist-row__top"><span className="db-skeleton-line db-skeleton-line--label-sm" /><span className="db-skeleton-line db-skeleton-line--value-xs" /></div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="db-actions">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="db-action db-skeleton-action">
            <span className="db-skeleton-line db-skeleton-line--action" />
          </div>
        ))}
      </div>
    </>
  )
}

function getDurationParts(valueMs: number) {
  if (valueMs >= 1000) {
    const value = valueMs / 1000
    return {
      value,
      unit: 's',
      decimals: 1,
      numeric: value.toLocaleString('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
    }
  }

  return {
    value: valueMs,
    unit: 'ms',
    decimals: 0,
    numeric: Math.round(valueMs).toLocaleString('fr-FR'),
  }
}