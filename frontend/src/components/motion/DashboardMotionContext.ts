import { createContext } from 'react'

export type DashboardMotionContextValue = {
  reducedMotion: boolean
}

export const DashboardMotionContext = createContext<DashboardMotionContextValue | null>(null)