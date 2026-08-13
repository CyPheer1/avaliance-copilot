import type { PropsWithChildren } from 'react'
import { DashboardMotionContext } from './DashboardMotionContext.ts'

export function DashboardMotionProvider({
  children,
  value,
}: PropsWithChildren<{ value: { reducedMotion: boolean } }>) {
  return <DashboardMotionContext.Provider value={value}>{children}</DashboardMotionContext.Provider>
}