import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { JWT_TOKEN_KEY } from './services/api'
import SideNav from './components/common/SideNav'
import TopBar from './components/common/TopBar'
import AssistantPanel from './components/assistant/AssistantPanel'
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
import NoAccessGate from './components/common/NoAccessGate'
import ErrorBoundary from './components/common/ErrorBoundary'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const hasToken = !!localStorage.getItem(JWT_TOKEN_KEY)
  if (!hasToken) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}

export default function App() {
  const [assistantOpen, setAssistantOpen] = useState(false)
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
            <ProtectedRoute>
              <CurrentUserProvider>
                <SideNav />
                <TopBar onOpenAssistant={() => setAssistantOpen(true)} />
                <AssistantPanel open={assistantOpen} onClose={() => setAssistantOpen(false)} />
                <NoAccessGate appName="payguard">
                  <main className="ml-56 min-h-screen bg-gray-100 p-6 pt-16 transition-all duration-200">
                    <ErrorBoundary>
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
                    </ErrorBoundary>
                  </main>
                </NoAccessGate>
              </CurrentUserProvider>
            </ProtectedRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  )
}
