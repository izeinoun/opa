import { useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import SideNav from './components/common/SideNav'
import TopBar from './components/common/TopBar'
import AssistantPanel from './components/assistant/AssistantPanel'
import DemoGate from './components/common/DemoGate'
import DashboardPage from './pages/DashboardPage'
import WorklistPage from './pages/WorklistPage'
import ClosedCasesPage from './pages/ClosedCasesPage'
import CaseDetailPage from './pages/CaseDetailPage'
import AdminPage from './pages/AdminPage'
import Analyze835Page from './pages/Analyze835Page'
import MembersPage from './pages/MembersPage'
import FeeSchedulesPage from './pages/FeeSchedulesPage'
import ApprovalsPage from './pages/ApprovalsPage'
import AssignmentsPage from './pages/AssignmentsPage'
import EscalationsPage from './pages/EscalationsPage'
import ProviderRiskPage from './pages/ProviderRiskPage'
import FileIntakePage from './pages/FileIntakePage'
import UnmatchedDocumentsPage from './pages/UnmatchedDocumentsPage'
import OutputFilesPage from './pages/OutputFilesPage'
import CaseQueuePage from './pages/CaseQueuePage'
import { CurrentUserProvider } from './hooks/useCurrentUser'
import NoAccessGate from './components/common/NoAccessGate'
import ErrorBoundary from './components/common/ErrorBoundary'

export default function App() {
  const [assistantOpen, setAssistantOpen] = useState(false)
  return (
    <BrowserRouter>
      <DemoGate>
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
            <Route path="/recoup-sent"   element={
              <CaseQueuePage
                title="Sent / In Recovery"
                subtitle="Recoupment letter sent — awaiting or processing recovery."
                statuses={['notice_sent', 'reconciling']}
                emptyText="No cases awaiting recovery."
              />} />
            <Route path="/recovered"     element={
              <CaseQueuePage
                title="Recovered"
                subtitle="Recouped and reconciled — recovery complete."
                statuses={['closed_recovered']}
                emptyText="No recovered cases yet."
              />} />
            <Route path="/not-for-recoup" element={
              <CaseQueuePage
                title="Not for Recoup"
                subtitle="Closed without pursuing recovery."
                statuses={['closed_not_for_recoup']}
                emptyText="No cases closed as not-for-recoup."
              />} />
            <Route path="/cases/:caseId" element={<CaseDetailPage />} />
            <Route path="/admin"         element={<AdminPage />} />
            <Route path="/analyze-835"   element={<Analyze835Page />} />
            <Route path="/members"       element={<MembersPage />} />
            <Route path="/fee-schedules" element={<FeeSchedulesPage />} />
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
      </DemoGate>
    </BrowserRouter>
  )
}
