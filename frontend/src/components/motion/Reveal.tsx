import { motion, useInView, useReducedMotion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import type { PropsWithChildren } from 'react'

type RevealProps = PropsWithChildren<{
  delay?: number
  y?: number
  className?: string
}>

export function Reveal({ children, delay = 0, y = 8, className }: RevealProps) {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, amount: 0.2 })
  const reducedMotion = useReducedMotion()
  const [willChange, setWillChange] = useState(true)

  useEffect(() => {
    if (!inView || reducedMotion) {
      return
    }
    const id = requestAnimationFrame(() => setWillChange(false))
    return () => cancelAnimationFrame(id)
  }, [inView, reducedMotion])

  if (reducedMotion) {
    return (
      <div ref={ref} className={className} style={{ height: '100%' }}>
        {children}
      </div>
    )
  }

  return (
    <motion.div
      ref={ref}
      className={className}
      style={{ height: '100%', willChange: willChange ? 'transform, opacity' : undefined }}
      initial={{ opacity: 0, y }}
      animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y }}
      transition={{ duration: 0.3, delay: delay / 1000, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  )
}