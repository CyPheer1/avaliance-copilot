import type { Variants } from 'motion/react'

const createContainerVariants = (staggerChildren: number, delayChildren: number): Variants => ({
  hidden: {},
  show: {
    transition: {
      staggerChildren,
      delayChildren,
    },
  },
})

export const containerVariants = createContainerVariants(0.07, 0.09)
export const compactContainerVariants = createContainerVariants(0.04, 0.04)

export const itemVariants: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.3,
      ease: [0.16, 1, 0.3, 1],
    },
  },
}