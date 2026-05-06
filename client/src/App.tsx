import { BrowserRouter, Routes, Route } from 'react-router-dom'
import SideNav from './components/common/SideNav'
import DashboardPage from './pages/DashboardPage'
import WorklistPage from './pages/WorklistPage'
import ClosedCasesPage from './pages/ClosedCasesPage'
import CaseDetailPage from './pages/CaseDetailPage'
import LetterPage from './pages/LetterPage'
import AdminPage from './pages/AdminPage'
import Analyze835Page from './pages/Analyze835Page'
import MembersPage from './pages/MembersPage'
import TrainModelPage from './pages/TrainModelPage'
import FeeSchedulesPage from './pages/FeeSchedulesPage'

export default function App() {
  return (
    <BrowserRouter>
      <SideNav />
      <main className="ml-56 min-h-screen bg-gray-100 p-6 transition-all duration-200">
        <Routes>
          <Route path="/"              element={<DashboardPage />} />
          <Route path="/worklist"      element={<WorklistPage />} />
          <Route path="/closed-cases"  element={<ClosedCasesPage />} />
          <Route path="/cases/:caseId" element={<CaseDetailPage />} />
          <Route path="/letters"       element={<LetterPage />} />
          <Route path="/admin"         element={<AdminPage />} />
          <Route path="/analyze-835"   element={<Analyze835Page />} />
          <Route path="/members"       element={<MembersPage />} />
          <Route path="/train-model"   element={<TrainModelPage />} />
          <Route path="/fee-schedules" element={<FeeSchedulesPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
