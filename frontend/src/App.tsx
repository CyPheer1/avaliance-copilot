import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AdminRoute } from './auth/AdminRoute.tsx'
import { ProtectedRoute } from './auth/ProtectedRoute.tsx'
import { AppShell } from './components/AppShell.tsx'
import { RouteErrorBoundary } from './components/RouteErrorBoundary.tsx'
import { DocumentsPage } from './pages/DocumentsPage.tsx'
import { LoginPage } from './pages/LoginPage.tsx'
import { MissionDetailPage } from './pages/MissionDetailPage.tsx'
import { MissionsPage } from './pages/MissionsPage.tsx'
import { RfpPage } from './pages/RfpPage.tsx'
import { SearchPage } from './pages/SearchPage.tsx'
import { UsersPage } from './pages/UsersPage.tsx'

const DashboardPage = lazy(() => import('./pages/DashboardPage.tsx').then((module) => ({ default: module.DashboardPage })))

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route element={<RouteErrorBoundary />}>
            <Route index element={<Navigate to="/tableau-de-bord" replace />} />
            <Route path="/tableau-de-bord" element={<Suspense fallback={<div className="page db-page" />}><DashboardPage /></Suspense>} />
            <Route path="/recherche" element={<SearchPage />} />
            <Route path="/propositions" element={<RfpPage />} />
          <Route path="/missions" element={<MissionsPage />} />
          <Route path="/missions/:missionId" element={<MissionDetailPage />} />
            <Route element={<AdminRoute />}>
              <Route path="/documents" element={<DocumentsPage />} />
              <Route path="/utilisateurs" element={<UsersPage />} />
            </Route>
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/tableau-de-bord" replace />} />
    </Routes>
  )
}

export default App
