import { useEffect, useRef } from 'react'

type KnowledgeNode = {
  x: number
  y: number
  radius: number
  kind: 'source' | 'knowledge' | 'ai' | 'verified'
  phase: number
}

type KnowledgeEdge = {
  from: number
  to: number
  phase: number
}

const FRAME_INTERVAL = 1000 / 30
const MAX_DPR = 1.5

const NODE_LAYOUT: KnowledgeNode[] = [
  { x: 0.08, y: 0.14, radius: 2.1, kind: 'source', phase: 0.4 },
  { x: 0.19, y: 0.08, radius: 2.8, kind: 'knowledge', phase: 1.1 },
  { x: 0.31, y: 0.2, radius: 2.2, kind: 'source', phase: 2.5 },
  { x: 0.44, y: 0.1, radius: 3, kind: 'ai', phase: 0.7 },
  { x: 0.57, y: 0.24, radius: 2, kind: 'knowledge', phase: 3.2 },
  { x: 0.73, y: 0.13, radius: 2.5, kind: 'source', phase: 1.8 },
  { x: 0.9, y: 0.22, radius: 2.2, kind: 'verified', phase: 2.1 },
  { x: 0.13, y: 0.42, radius: 2.4, kind: 'knowledge', phase: 2.8 },
  { x: 0.27, y: 0.51, radius: 2, kind: 'source', phase: 0.2 },
  { x: 0.4, y: 0.39, radius: 2.6, kind: 'knowledge', phase: 1.5 },
  { x: 0.55, y: 0.55, radius: 3.1, kind: 'ai', phase: 2.4 },
  { x: 0.7, y: 0.43, radius: 2.1, kind: 'source', phase: 3.7 },
  { x: 0.85, y: 0.54, radius: 2.6, kind: 'knowledge', phase: 0.9 },
  { x: 0.07, y: 0.73, radius: 2.1, kind: 'source', phase: 1.9 },
  { x: 0.22, y: 0.84, radius: 2.7, kind: 'verified', phase: 3.4 },
  { x: 0.38, y: 0.7, radius: 2.2, kind: 'knowledge', phase: 0.6 },
  { x: 0.52, y: 0.82, radius: 2.5, kind: 'source', phase: 2.9 },
  { x: 0.67, y: 0.69, radius: 2.2, kind: 'knowledge', phase: 1.3 },
  { x: 0.81, y: 0.8, radius: 3, kind: 'ai', phase: 3.8 },
  { x: 0.94, y: 0.7, radius: 2, kind: 'source', phase: 0.3 },
]

const EDGES: KnowledgeEdge[] = [
  { from: 0, to: 1, phase: 0.1 }, { from: 1, to: 2, phase: 0.7 },
  { from: 2, to: 3, phase: 1.2 }, { from: 3, to: 4, phase: 1.8 },
  { from: 4, to: 5, phase: 2.4 }, { from: 5, to: 6, phase: 3 },
  { from: 0, to: 7, phase: 1.6 }, { from: 2, to: 9, phase: 2.2 },
  { from: 4, to: 10, phase: 2.8 }, { from: 6, to: 12, phase: 3.4 },
  { from: 7, to: 8, phase: 0.4 }, { from: 8, to: 9, phase: 1 },
  { from: 9, to: 10, phase: 1.6 }, { from: 10, to: 11, phase: 2.2 },
  { from: 11, to: 12, phase: 2.8 }, { from: 7, to: 13, phase: 3.4 },
  { from: 8, to: 14, phase: 0.8 }, { from: 10, to: 16, phase: 1.4 },
  { from: 12, to: 18, phase: 2 }, { from: 13, to: 14, phase: 2.6 },
  { from: 14, to: 15, phase: 3.2 }, { from: 15, to: 16, phase: 0.5 },
  { from: 16, to: 17, phase: 1.1 }, { from: 17, to: 18, phase: 1.7 },
  { from: 18, to: 19, phase: 2.3 },
]

const NODE_COLORS = {
  source: '#8eabc3',
  knowledge: '#2783de',
  ai: '#7356c8',
  verified: '#b3c92d',
}

export function LivingKnowledgeField() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined

    const context = canvas.getContext('2d', { alpha: true })
    if (!context) return undefined

    const reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    let width = 1
    let height = 1
    let frame = 0
    let lastFrame = 0
    let reducedMotion = reducedMotionQuery.matches

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      width = Math.max(1, Math.round(rect.width))
      height = Math.max(1, Math.round(rect.height))
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR)
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      draw(performance.now())
    }

    const point = (node: KnowledgeNode, time: number) => ({
      x: node.x * width + Math.sin(time * 0.00008 + node.phase) * 7,
      y: node.y * height + Math.cos(time * 0.00007 + node.phase) * 5,
    })

    const drawDocument = (x: number, y: number, alpha: number) => {
      context.save()
      context.globalAlpha = alpha
      context.strokeStyle = '#6f91ad'
      context.lineWidth = 0.8
      context.strokeRect(x - 5, y - 6, 10, 12)
      context.beginPath()
      context.moveTo(x - 2.5, y - 2)
      context.lineTo(x + 2.5, y - 2)
      context.moveTo(x - 2.5, y + 1)
      context.lineTo(x + 1.5, y + 1)
      context.stroke()
      context.restore()
    }

    const draw = (time: number) => {
      context.clearRect(0, 0, width, height)
      const points = NODE_LAYOUT.map((node) => point(node, reducedMotion ? 0 : time))

      context.lineWidth = 0.75
      EDGES.forEach((edge, edgeIndex) => {
        const from = points[edge.from]
        const to = points[edge.to]
        context.strokeStyle = 'rgba(108, 143, 171, 0.16)'
        context.beginPath()
        context.moveTo(from.x, from.y)
        context.lineTo(to.x, to.y)
        context.stroke()

        if (!reducedMotion && edgeIndex % 4 === 0) {
          const progress = (time * 0.000025 + edge.phase) % 1
          const x = from.x + (to.x - from.x) * progress
          const y = from.y + (to.y - from.y) * progress
          const gradient = context.createRadialGradient(x, y, 0, x, y, 6)
          gradient.addColorStop(0, 'rgba(39, 131, 222, 0.28)')
          gradient.addColorStop(1, 'rgba(39, 131, 222, 0)')
          context.fillStyle = gradient
          context.beginPath()
          context.arc(x, y, 6, 0, Math.PI * 2)
          context.fill()
        }
      })

      points.forEach(({ x, y }, index) => {
        const node = NODE_LAYOUT[index]
        if (node.kind === 'source' && index % 2 === 0) {
          drawDocument(x, y, 0.32)
          return
        }

        context.globalAlpha = node.kind === 'verified' ? 0.45 : 0.32
        context.fillStyle = NODE_COLORS[node.kind]
        context.beginPath()
        context.arc(x, y, node.radius, 0, Math.PI * 2)
        context.fill()
      })
      context.globalAlpha = 1
    }

    const animate = (time: number) => {
      if (time - lastFrame >= FRAME_INTERVAL) {
        lastFrame = time
        draw(time)
      }
      frame = window.requestAnimationFrame(animate)
    }

    const syncMotion = () => {
      reducedMotion = reducedMotionQuery.matches
      window.cancelAnimationFrame(frame)
      if (reducedMotion) draw(0)
      else frame = window.requestAnimationFrame(animate)
    }

    const syncVisibility = () => {
      window.cancelAnimationFrame(frame)
      if (!document.hidden && !reducedMotion) frame = window.requestAnimationFrame(animate)
    }

    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(canvas)
    reducedMotionQuery.addEventListener('change', syncMotion)
    document.addEventListener('visibilitychange', syncVisibility)
    resize()
    syncMotion()

    return () => {
      window.cancelAnimationFrame(frame)
      resizeObserver.disconnect()
      reducedMotionQuery.removeEventListener('change', syncMotion)
      document.removeEventListener('visibilitychange', syncVisibility)
    }
  }, [])

  return <canvas ref={canvasRef} className="living-knowledge-field" aria-hidden="true" />
}