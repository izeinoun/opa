import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { initAuth } from './services/authService'
import AuthenticatedLayout from './components/layout/AuthenticatedLayout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import WorklistPage from './pages/WorklistPage'
import ClosedCasesPage from './pages/ClosedCasesPage'
import CaseDetailPage from './pages/CaseDetailPage'
import AdminPage from './pages/AdminPage'
import Analyze835Page from './pages/Analyze835Page'
import MembersPage from './pages/MembersPage'
import FeeSchedulesPage from './pages/FeeSchedulesPage'
import ProviderOrgDetailPage from './pages/ProviderOrgDetailPage'
import ProvidersPage from './pages/ProvidersPage'
import ApprovalsPage from './pages/ApprovalsPage'
import AssignmentsPage from './pages/AssignmentsPage'
import EscalationsPage from './pages/EscalationsPage'
import ProviderRiskPage from './pages/ProviderRiskPage'
import FileIntakePage from './pages/FileIntakePage'
import UnmatchedDocumentsPage from './pages/UnmatchedDocumentsPage'
import OutputFilesPage from './pages/OutputFilesPage'
import DeliveryQueuePage from './pages/DeliveryQueuePage'
import SecureDownloadPage from './pages/SecureDownloadPage'
import { CurrentUserProvider } from './hooks/useCurrentUser'

function ProtectedRoute({ children, isAuthenticated, isLoading }: { children: React.ReactNode; isAuthenticated: boolean; isLoading: boolean }) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4" />
          <p className="text-gray-600">Loading...</p>
        </div>
      </div>
    )
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // Check if user is already logged in via cookie on mount
    initAuth({
      onAuthChange: (user) => {
        setIsAuthenticated(!!user)
      },
    }).then((user) => {
      setIsAuthenticated(!!user)
      setIsLoading(false)
    })
  }, [])

  return (
    <BrowserRouter>
        <Routes>
        {/* Public-facing pages (no auth required) */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/secure-download" element={<SecureDownloadPage />} />

        {/* Authenticated app */}
        <Route
          path="*"
          element={
            <ProtectedRoute isAuthenticated={isAuthenticated} isLoading={isLoading}>
              <CurrentUserProvider>
                <AuthenticatedLayout>
                  <Routes>
                        <Route path="/"              element={<DashboardPage />} />
                        <Route path="/worklist"      element={<WorklistPage />} />
                        <Route path="/closed-cases"  element={<ClosedCasesPage />} />
                        {/* Legacy queue routes now fold into the Worklist stage tabs
                            (Recovery) and the Closed page tabs (recovered / not-for-recoup). */}
                        <Route path="/recoup-sent"    element={<Navigate to="/worklist?stage=recovery" replace />} />
                        <Route path="/recovered"      element={<Navigate to="/closed-cases?status=closed_recovered" replace />} />
                        <Route path="/not-for-recoup" element={<Navigate to="/closed-cases?status=closed_not_for_recoup" replace />} />
                        <Route path="/cases/:caseId" element={<CaseDetailPage />} />
                        <Route path="/admin"         element={<AdminPage />} />
                        <Route path="/analyze-835"   element={<Analyze835Page />} />
                        <Route path="/members"       element={<MembersPage />} />
                        <Route path="/fee-schedules" element={<FeeSchedulesPage />} />
                        <Route path="/providers"     element={<ProvidersPage />} />
                        <Route path="/providers/:orgId" element={<ProviderOrgDetailPage />} />
                        <Route path="/delivery-queue" element={<DeliveryQueuePage />} />
                        <Route path="/approvals"     element={<ApprovalsPage />} />
                        <Route path="/assignments"   element={<AssignmentsPage />} />
                        <Route path="/escalations"   element={<EscalationsPage />} />
                        <Route path="/provider-risk" element={<ProviderRiskPage />} />
                        <Route path="/file-intake"   element={<FileIntakePage />} />
                        <Route path="/file-intake/unmatched" element={<UnmatchedDocumentsPage />} />
                        <Route path="/output-files"  element={<OutputFilesPage />} />
                  </Routes>
                </AuthenticatedLayout>
              </CurrentUserProvider>
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
