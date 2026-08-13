import { useContext } from 'react'
import { DashboardMotionContext } from './DashboardMotionContext.ts'

export function useDashboardMotion() {
  const context = useContext(DashboardMotionContext)
  if (!context) {
    throw new Error('useDashboardMotion must be used within a DashboardMotionProvider')
  }
  return context
}