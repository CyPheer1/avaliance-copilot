import { useEffect, useMemo, useRef } from 'react'

type EvidenceGraphProps = {
  className?: string
  reducedMotion?: boolean
}

type NodeKind = 'neutral' | 'medium' | 'accent'

type GraphNode = {
  id: number
  x: number
  y: number
  radius: number
  kind: NodeKind
  driftX: number
  driftY: number
  period: number
  phase: number
  appearDelay: number
}

type GraphEdge = {
  id: number
  from: number
  to: number
  length: number
  appearAt: number
}

type SafeZone = {
  left: number
  top: number
  right: number
  bottom: number
}

type Scene = {
  width: number
  height: number
  nodes: GraphNode[]
  edges: GraphEdge[]
  accentNodes: number[]
  accentKinds: Map<number, 'violet' | 'blue' | 'accent'>
  safeZone: SafeZone
}

type PointerState = {
  x: number
  y: number
  targetX: number
  targetY: number
}

const INTRO_DURATION = 1400
const FRAME_BUDGET = 1000 / 60
const IMPULSE_INTERVAL = 3500
const IMPULSE_DURATION = 900
const MAX_DPR = 2
const NODE_HALO = 14
const NODE_REACT_RADIUS = 90
const NODE_PARALLAX_MAX = 12
const NODE_COUNT = 24
const SAFE_ZONE_X = 0.62
const SAFE_ZONE_Y = 0.46
const NODE_MARGIN_X = 72
const NODE_MARGIN_Y = 56

export function EvidenceGraph({ className = '', reducedMotion = false }: EvidenceGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const sceneRef = useRef<Scene | null>(null)
  const frameRef = useRef<number | null>(null)
  const resizeTimerRef = useRef<number | null>(null)
  const visibleRef = useRef(true)
  const runningRef = useRef(false)
  const lastFrameRef = useRef(0)
  const lastImpulseRef = useRef(0)
  const impulseEdgeIndexRef = useRef(0)
  const impulseActiveRef = useRef(false)
  const introPulseDoneRef = useRef(false)
  const pointerRef = useRef<PointerState>({ x: 0, y: 0, targetX: 0, targetY: 0 })
  const rafTokenRef = useRef(0)

  const baseClassName = useMemo(() => ['login-graph', className].filter(Boolean).join(' '), [className])

  useEffect(() => {
    const canvas = canvasRef.current
    const wrapper = wrapperRef.current
    if (!canvas || !wrapper) {
      return undefined
    }

    const context = canvas.getContext('2d', { alpha: true })
    if (!context) {
      return undefined
    }

    const setupScene = () => {
      const rect = wrapper.getBoundingClientRect()
      const width = Math.max(1, Math.floor(rect.width))
      const height = Math.max(1, Math.floor(rect.height))
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR)
      canvas.width = Math.max(1, Math.floor(width * dpr))
      canvas.height = Math.max(1, Math.floor(height * dpr))
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
      sceneRef.current = buildScene(width, height)
      pointerRef.current = {
        x: width * 0.68,
        y: height * 0.24,
        targetX: width * 0.68,
        targetY: height * 0.24,
      }
      lastFrameRef.current = 0
      lastImpulseRef.current = 0
      impulseEdgeIndexRef.current = 0
      impulseActiveRef.current = false
      introPulseDoneRef.current = false
      drawFrame(0)
    }

    const stopLoop = () => {
      if (frameRef.current !== null) {
        window.cancelAnimationFrame(frameRef.current)
        frameRef.current = null
      }
      runningRef.current = false
    }

    const startLoop = () => {
      if (runningRef.current || reducedMotion || !visibleRef.current || document.hidden) {
        return
      }

      runningRef.current = true
      rafTokenRef.current += 1
      const token = rafTokenRef.current
      const start = performance.now()

      const tick = (now: number) => {
        if (token !== rafTokenRef.current) {
          return
        }

        if (!visibleRef.current || document.hidden) {
          stopLoop()
          return
        }

        if (lastFrameRef.current && now - lastFrameRef.current < FRAME_BUDGET - 1) {
          frameRef.current = window.requestAnimationFrame(tick)
          return
        }

        lastFrameRef.current = now
        drawFrame(now - start)
        frameRef.current = window.requestAnimationFrame(tick)
      }

      frameRef.current = window.requestAnimationFrame(tick)
    }

    const drawFrame = (elapsed: number) => {
      const scene = sceneRef.current
      const canvasContext = context
      if (!scene) {
        return
      }

      const { width, height, nodes, edges, accentNodes, safeZone } = scene
      canvasContext.clearRect(0, 0, width, height)

      const pointer = pointerRef.current
      pointer.x += (pointer.targetX - pointer.x) * 0.08
      pointer.y += (pointer.targetY - pointer.y) * 0.08
      const rawParallaxX = clamp((width * 0.55 - pointer.x) * 0.028, -NODE_PARALLAX_MAX, NODE_PARALLAX_MAX)
      const rawParallaxY = clamp((height * 0.28 - pointer.y) * 0.028, -NODE_PARALLAX_MAX, NODE_PARALLAX_MAX)

      const nodeStates = nodes.map((node) => {
        const appear = reducedMotion ? 1 : clamp((elapsed - node.appearDelay) / 220, 0, 1)
        const drift = reducedMotion
          ? { x: 0, y: 0 }
          : {
              x: Math.sin(elapsed / node.period + node.phase) * node.driftX,
              y: Math.cos(elapsed / (node.period * 0.87) + node.phase * 1.31) * node.driftY,
            }
        const parallax = clampOffsetToSafeZone(node, safeZone, rawParallaxX, rawParallaxY)
        const driftOffset = clampOffsetToSafeZone(node, safeZone, drift.x, drift.y)
        const worldX = node.x + driftOffset.x + parallax.x
        const worldY = node.y + driftOffset.y + parallax.y
        const pointerDistance = distance(worldX, worldY, pointer.x, pointer.y)
        const hoverBoost = clamp(1 - pointerDistance / NODE_REACT_RADIUS, 0, 1)
        const hoverRadius = hoverBoost * 1.5
        const opacity = 0.35 + appear * 0.65 + hoverBoost * 0.2
        return { ...node, appear, worldX, worldY, hoverBoost, hoverRadius, opacity }
      })

      if (!reducedMotion) {
        if (!introPulseDoneRef.current && elapsed >= INTRO_DURATION + 110) {
          introPulseDoneRef.current = true
        }

        if (!impulseActiveRef.current && elapsed - lastImpulseRef.current >= IMPULSE_INTERVAL) {
          impulseActiveRef.current = true
          lastImpulseRef.current = elapsed
          impulseEdgeIndexRef.current = (impulseEdgeIndexRef.current + 1) % Math.max(1, edges.length)
        }
      }

      canvasContext.strokeStyle = 'rgba(216, 225, 234, 0.88)'
      canvasContext.lineWidth = 1
      canvasContext.lineCap = 'round'

      edges.forEach((edge, edgeIndex) => {
        const from = nodeStates[edge.from]
        const to = nodeStates[edge.to]
        const edgeStart = Math.max(from.appearDelay, to.appearDelay) + 120
        const drawProgress = reducedMotion ? 1 : clamp((elapsed - edgeStart) / 400, 0, 1)
        if (drawProgress <= 0) {
          return
        }

        const sx = from.worldX
        const sy = from.worldY
        const ex = to.worldX
        const ey = to.worldY
        if (segmentIntersectsRect(sx, sy, ex, ey, safeZone)) {
          return
        }

        const dx = ex - sx
        const dy = ey - sy
        const progress = easeOutCubic(drawProgress)
        const mx = sx + dx * progress
        const my = sy + dy * progress

        canvasContext.save()
        canvasContext.globalAlpha = 0.28 + Math.min(from.appear, to.appear) * 0.42
        canvasContext.beginPath()
        canvasContext.moveTo(sx, sy)
        canvasContext.lineTo(mx, my)
        canvasContext.stroke()
        canvasContext.restore()

        const isImpulseEdge = !reducedMotion && edgeIndex === impulseEdgeIndexRef.current && impulseActiveRef.current
        if (isImpulseEdge) {
          const impulseElapsed = elapsed - lastImpulseRef.current
          const impulseProgress = clamp(impulseElapsed / IMPULSE_DURATION, 0, 1)
          const trail = 0.18
          const head = edge.length === 0 ? 1 : easeOutCubic(impulseProgress)
          const tail = clamp(head - trail, 0, 1)
          const ix = sx + dx * head
          const iy = sy + dy * head
          const tx = sx + dx * tail
          const ty = sy + dy * tail
          const gradient = canvasContext.createLinearGradient(tx, ty, ix, iy)
          gradient.addColorStop(0, 'rgba(94,130,166,0)')
          gradient.addColorStop(0.6, 'rgba(94,130,166,0.25)')
          gradient.addColorStop(1, 'rgba(94,130,166,0.95)')
          canvasContext.save()
          canvasContext.strokeStyle = gradient
          canvasContext.lineWidth = 2
          canvasContext.beginPath()
          canvasContext.moveTo(tx, ty)
          canvasContext.lineTo(ix, iy)
          canvasContext.stroke()
          canvasContext.restore()
          canvasContext.save()
          canvasContext.fillStyle = '#5E82A6'
          canvasContext.beginPath()
          canvasContext.arc(ix, iy, 2, 0, Math.PI * 2)
          canvasContext.fill()
          canvasContext.restore()
          if (impulseProgress >= 1) {
            impulseActiveRef.current = false
          }
        }
      })

      nodeStates.forEach((node, index) => {
        const accentPulse = !reducedMotion && accentNodes.includes(node.id) && introPulseDoneRef.current
          ? clamp(1 - Math.abs((elapsed - (INTRO_DURATION + 160)) / 320 - 0.5) * 2, 0, 1)
          : 0
        const baseRadius = node.radius + node.hoverRadius
        const finalRadius = baseRadius + (node.hoverBoost * 1.5)
        const alpha = reducedMotion ? 1 : clamp(node.opacity, 0, 1)

        if (node.kind !== 'neutral') {
          canvasContext.save()
          canvasContext.globalAlpha = 0.12 * (1 + accentPulse)
          canvasContext.fillStyle = specialNodeFill(scene.accentKinds.get(node.id))
          canvasContext.beginPath()
          canvasContext.arc(node.worldX, node.worldY, finalRadius + NODE_HALO, 0, Math.PI * 2)
          canvasContext.fill()
          canvasContext.restore()
        }

        canvasContext.save()
        canvasContext.globalAlpha = alpha
        canvasContext.fillStyle = node.kind === 'accent' ? specialNodeFill(scene.accentKinds.get(node.id)) : node.kind === 'medium' ? '#5E82A6' : '#BFCEDB'
        canvasContext.beginPath()
        canvasContext.arc(node.worldX, node.worldY, finalRadius, 0, Math.PI * 2)
        canvasContext.fill()
        canvasContext.restore()

        if (accentNodes.includes(node.id) && introPulseDoneRef.current) {
          const pulseProgress = clamp((elapsed - (INTRO_DURATION + 100 + index * 8)) / 420, 0, 1)
          if (pulseProgress > 0) {
            canvasContext.save()
            canvasContext.globalAlpha = (1 - pulseProgress) * 0.12
            canvasContext.fillStyle = specialNodeFill(scene.accentKinds.get(node.id))
            canvasContext.beginPath()
            canvasContext.arc(node.worldX, node.worldY, finalRadius + 16 * pulseProgress, 0, Math.PI * 2)
            canvasContext.fill()
            canvasContext.restore()
          }
        }
      })
    }

    const handlePointerMove = (event: PointerEvent) => {
      const rect = wrapper.getBoundingClientRect()
      pointerRef.current.targetX = event.clientX - rect.left
      pointerRef.current.targetY = event.clientY - rect.top
    }

    const handlePointerLeave = () => {
      const rect = wrapper.getBoundingClientRect()
      pointerRef.current.targetX = rect.width * 0.68
      pointerRef.current.targetY = rect.height * 0.24
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        stopLoop()
        return
      }
      if (visibleRef.current) {
        startLoop()
      }
    }

    const handleResize = () => {
      if (resizeTimerRef.current !== null) {
        window.clearTimeout(resizeTimerRef.current)
      }
      resizeTimerRef.current = window.setTimeout(() => {
        setupScene()
        if (!reducedMotion) {
          startLoop()
        }
      }, 150)
    }

    const resizeObserver = new ResizeObserver(handleResize)
    const intersectionObserver = new IntersectionObserver((entries) => {
      visibleRef.current = entries[0]?.isIntersecting ?? true
      if (visibleRef.current && !reducedMotion && !document.hidden) {
        startLoop()
      } else {
        stopLoop()
      }
    }, { threshold: 0.1 })

    setupScene()
    wrapper.addEventListener('pointermove', handlePointerMove)
    wrapper.addEventListener('pointerleave', handlePointerLeave)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    resizeObserver.observe(wrapper)
    intersectionObserver.observe(wrapper)

    if (!reducedMotion) {
      startLoop()
    }

    return () => {
      stopLoop()
      resizeObserver.disconnect()
      intersectionObserver.disconnect()
      wrapper.removeEventListener('pointermove', handlePointerMove)
      wrapper.removeEventListener('pointerleave', handlePointerLeave)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      if (resizeTimerRef.current !== null) {
        window.clearTimeout(resizeTimerRef.current)
      }
    }
  }, [reducedMotion])

  return (
    <div ref={wrapperRef} className={baseClassName} aria-hidden="true">
      <canvas ref={canvasRef} className="login-graph__canvas" />
    </div>
  )
}

function buildScene(width: number, height: number): Scene {
  const rng = mulberry32(0x4c6f6769)
  const safeZone = getSafeZone(width, height)
  const centers = [
    { x: width * 0.72, y: height * 0.18 },
    { x: width * 0.56, y: height * 0.18 },
    { x: width * 0.83, y: height * 0.28 },
    { x: width * 0.66, y: height * 0.34 },
    { x: width * 0.42, y: height * 0.24 },
    { x: width * 0.76, y: height * 0.48 },
    { x: width * 0.58, y: height * 0.52 },
  ]
  const nodes: GraphNode[] = []

  for (let index = 0; index < NODE_COUNT; index += 1) {
    const group = index % centers.length
    const center = centers[group]
    let created = false

    for (let attempt = 0; attempt < 120 && !created; attempt += 1) {
      const angle = (index / NODE_COUNT) * Math.PI * 2.1 + group * 0.57 + attempt * 0.09
      const radiusBias = 26 + (index % 5) * 15 + group * 4 + attempt * 0.12
      const candidateX = clamp(center.x + Math.cos(angle) * radiusBias + (rng() - 0.5) * 34, NODE_MARGIN_X, width - NODE_MARGIN_X)
      const candidateY = clamp(center.y + Math.sin(angle * 1.14) * (24 + group * 9) + (rng() - 0.5) * 30, NODE_MARGIN_Y, height - NODE_MARGIN_Y)
      if (isPointInsideRect(candidateX, candidateY, safeZone)) {
        continue
      }
      if (nodes.some((node) => distance(node.x, node.y, candidateX, candidateY) < 34)) {
        continue
      }

      nodes.push({
        id: index,
        x: candidateX,
        y: candidateY,
        radius: 2.2 + (index % 4) * 0.45 + (group === 1 ? 0.2 : 0),
        kind: 'neutral',
        driftX: 1.2 + rng() * 1,
        driftY: 1.2 + rng() * 1,
        period: 6000 + rng() * 6000,
        phase: rng() * Math.PI * 2,
        appearDelay: 0,
      })
      created = true
    }

    if (!created) {
      const fallback = fallbackNodePosition(width, height, safeZone, index)
      nodes.push({
        id: index,
        x: fallback.x,
        y: fallback.y,
        radius: 2.2 + (index % 4) * 0.45,
        kind: 'neutral',
        driftX: 1.1,
        driftY: 1.1,
        period: 7000,
        phase: rng() * Math.PI * 2,
        appearDelay: 0,
      })
    }
  }

  const accentNodes = [
    closestNode(nodes, width * 0.52, height * 0.18),
    closestNode(nodes, width * 0.68, height * 0.44),
    closestNode(nodes, width * 0.82, height * 0.24),
  ]
  const accentKinds = new Map<number, 'violet' | 'blue' | 'accent'>([
    [accentNodes[0], 'violet'],
    [accentNodes[1], 'accent'],
    [accentNodes[2], 'blue'],
  ])

  const mediumNodes = nodes
    .map((node) => node.id)
    .filter((id) => !accentNodes.includes(id))
    .sort((left, right) => distance(nodes[left].x, nodes[left].y, width * 0.55, height * 0.28) - distance(nodes[right].x, nodes[right].y, width * 0.55, height * 0.28))
    .slice(0, 4)

  nodes.forEach((node) => {
    if (accentNodes.includes(node.id)) {
      node.kind = 'accent'
    } else if (mediumNodes.includes(node.id)) {
      node.kind = 'medium'
    }
  })

  const ordered = [...nodes].sort((left, right) => distance(left.x, left.y, width * 0.55, height * 0.28) - distance(right.x, right.y, width * 0.55, height * 0.28))
  ordered.forEach((node, index) => {
    nodes[node.id].appearDelay = index * 35
  })

  const edgeMap = new Map<string, GraphEdge>()
  nodes.forEach((node) => {
    const nearest = [...nodes]
      .filter((candidate) => candidate.id !== node.id)
      .map((candidate) => ({ candidate, distance: distance(node.x, node.y, candidate.x, candidate.y) }))
      .filter(({ candidate, distance: edgeDistance }) => edgeDistance <= width * 0.24 && !segmentIntersectsRect(node.x, node.y, candidate.x, candidate.y, safeZone))
      .sort((left, right) => left.distance - right.distance)
      .slice(0, 3)

    nearest.forEach(({ candidate, distance: edgeDistance }) => {
      const from = Math.min(node.id, candidate.id)
      const to = Math.max(node.id, candidate.id)
      const key = `${from}-${to}`
      if (!edgeMap.has(key)) {
        edgeMap.set(key, {
          id: edgeMap.size,
          from,
          to,
          length: edgeDistance,
          appearAt: Math.max(nodes[from].appearDelay, nodes[to].appearDelay) + 120,
        })
      }
    })
  })

  const edges = [...edgeMap.values()].sort((left, right) => left.length - right.length).slice(0, 34)

  return { width, height, nodes, edges, accentNodes, accentKinds, safeZone }
}

function getSafeZone(width: number, height: number): SafeZone {
  return {
    left: 0,
    top: height * SAFE_ZONE_Y,
    right: width * SAFE_ZONE_X,
    bottom: height,
  }
}

function clampOffsetToSafeZone(node: GraphNode, safeZone: SafeZone, offsetX: number, offsetY: number) {
  const nextX = node.x + offsetX
  const nextY = node.y + offsetY
  if (!isPointInsideRect(nextX, nextY, safeZone)) {
    return { x: offsetX, y: offsetY }
  }

  const edgePushX = nextX <= safeZone.right ? safeZone.right - node.x + 12 : offsetX
  const edgePushY = nextY >= safeZone.top ? safeZone.top - node.y - 12 : offsetY

  const candidates = [
    { x: offsetX, y: edgePushY },
    { x: edgePushX, y: offsetY },
    { x: edgePushX, y: edgePushY },
    { x: 0, y: 0 },
  ]

  for (const candidate of candidates) {
    if (!isPointInsideRect(node.x + candidate.x, node.y + candidate.y, safeZone)) {
      return candidate
    }
  }

  return { x: 0, y: 0 }
}

function fallbackNodePosition(width: number, height: number, safeZone: SafeZone, index: number) {
  const columns = [0.42, 0.56, 0.68, 0.8]
  const rows = [0.16, 0.24, 0.34, 0.46, 0.58]
  const x = width * columns[index % columns.length]
  const y = height * rows[Math.floor(index / columns.length) % rows.length]
  if (!isPointInsideRect(x, y, safeZone)) {
    return { x, y }
  }
  return { x: width * 0.78, y: height * 0.24 }
}

function segmentIntersectsRect(x1: number, y1: number, x2: number, y2: number, rect: SafeZone) {
  if (isPointInsideRect(x1, y1, rect) || isPointInsideRect(x2, y2, rect)) {
    return true
  }

  return [
    [rect.left, rect.top, rect.right, rect.top],
    [rect.right, rect.top, rect.right, rect.bottom],
    [rect.right, rect.bottom, rect.left, rect.bottom],
    [rect.left, rect.bottom, rect.left, rect.top],
  ].some(([ax, ay, bx, by]) => segmentsIntersect(x1, y1, x2, y2, ax, ay, bx, by))
}

function isPointInsideRect(x: number, y: number, rect: SafeZone) {
  return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom
}

function segmentsIntersect(x1: number, y1: number, x2: number, y2: number, x3: number, y3: number, x4: number, y4: number) {
  const d1 = direction(x3, y3, x4, y4, x1, y1)
  const d2 = direction(x3, y3, x4, y4, x2, y2)
  const d3 = direction(x1, y1, x2, y2, x3, y3)
  const d4 = direction(x1, y1, x2, y2, x4, y4)

  if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) {
    return true
  }

  if (d1 === 0 && onSegment(x3, y3, x4, y4, x1, y1)) return true
  if (d2 === 0 && onSegment(x3, y3, x4, y4, x2, y2)) return true
  if (d3 === 0 && onSegment(x1, y1, x2, y2, x3, y3)) return true
  if (d4 === 0 && onSegment(x1, y1, x2, y2, x4, y4)) return true
  return false
}

function direction(ax: number, ay: number, bx: number, by: number, px: number, py: number) {
  return (px - ax) * (by - ay) - (py - ay) * (bx - ax)
}

function onSegment(ax: number, ay: number, bx: number, by: number, px: number, py: number) {
  return px >= Math.min(ax, bx) && px <= Math.max(ax, bx) && py >= Math.min(ay, by) && py <= Math.max(ay, by)
}

function closestNode(nodes: GraphNode[], x: number, y: number) {
  let best = 0
  let bestDistance = Number.POSITIVE_INFINITY
  nodes.forEach((node) => {
    const current = distance(node.x, node.y, x, y)
    if (current < bestDistance) {
      best = node.id
      bestDistance = current
    }
  })
  return best
}

function specialNodeFill(kind?: 'violet' | 'blue' | 'accent') {
  if (kind === 'violet') {
    return '#7B2FD6'
  }

  if (kind === 'blue') {
    return '#2783DE'
  }

  return '#12324E'
}

function mulberry32(seed: number) {
  let value = seed
  return () => {
    value += 0x6D2B79F5
    let t = Math.imul(value ^ (value >>> 15), 1 | value)
    t ^= t + Math.imul(t ^ (t >>> 7), 61 | t)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function distance(x1: number, y1: number, x2: number, y2: number) {
  return Math.hypot(x2 - x1, y2 - y1)
}

function easeOutCubic(value: number) {
  return 1 - Math.pow(1 - value, 3)
}
