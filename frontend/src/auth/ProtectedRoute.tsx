import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './auth-context.ts'

export function ProtectedRoute() {
  const { session } = useAuth()
  const location = useLocation()
  return session ? <Outlet /> : <Navigate to="/login" replace state={{ from: location.pathname }} />
}