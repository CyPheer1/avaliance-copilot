import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from './auth-context.ts'

export function AdminRoute() {
  const { session } = useAuth()
  return session?.role === 'ADMIN' ? <Outlet /> : <Navigate to="/recherche" replace />
}