// Main layout for authenticated PayGuard app.
// Structure: TopBar + (CollapsibleSideNav + Main Content + AssistantDrawer)
// Both SideNav and Assistant can be collapsed to give center content more space
import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { Menu } from 'lucide-react'
import SideNav from '../common/SideNav'
import TopBar from '../common/TopBar'
import AssistantDrawer from '../assistant/AssistantDrawer'
import NoAccessGate from '../common/NoAccessGate'
import ErrorBoundary from '../common/ErrorBoundary'
import { TourProvider, SpotlightTour, useTour } from '../walkthrough'
import type { ChatContext } from '../../types/assistant'

function deriveRouteContext(pathname: string): ChatContext {
  const m = pathname.match(/^\/cases\/(\d+)/)
  if (m) return { active_case_id: parseInt(m[1], 10), active_view: 'case' }
  if (pathname.startsWith('/worklist')) return { active_view: 'worklist' }
  if (pathname.startsWith('/closed-cases')) return { active_view: 'closed_cases' }
  if (pathname === '/' || pathname.startsWith('/dashboard')) return { active_view: 'dashboard' }
  return {}
}

interface Props {
  children: React.ReactNode
}

export default function AuthenticatedLayout({ children }: Props) {
  // The whole authenticated shell shares one tour engine so the TopBar help
  // button, the nav anchors, and the overlay all talk to the same state.
  return (
    <TourProvider app="payguard">
      <LayoutShell>{children}</LayoutShell>
    </TourProvider>
  )
}

function LayoutShell({ children }: Props) {
  // While the tour is running, force the nav open so its data-tour anchors
  // exist to spotlight (it defaults collapsed).
  const { isActive: tourActive } = useTour()
  const [navCollapsed, setNavCollapsed] = useState(() => {
    const saved = localStorage.getItem('payguard_nav_collapsed')
    return saved ? JSON.parse(saved) : true
  })

  const [assistantCollapsed, setAssistantCollapsed] = useState(() => {
    const saved = localStorage.getItem('payguard_assistant_collapsed')
    return saved ? JSON.parse(saved) : false
  })

  const [assistantWideMode, setAssistantWideMode] = useState(() => {
    const saved = localStorage.getItem('payguard_assistant_wide_mode')
    return saved ? JSON.parse(saved) : false
  })

  const location = useLocation()
  const assistantContext = deriveRouteContext(location.pathname)

  // Persist collapsed states
  useEffect(() => {
    localStorage.setItem('payguard_nav_collapsed', JSON.stringify(navCollapsed))
  }, [navCollapsed])

  useEffect(() => {
    localStorage.setItem('payguard_assistant_collapsed', JSON.stringify(assistantCollapsed))
  }, [assistantCollapsed])

  useEffect(() => {
    localStorage.setItem('payguard_assistant_wide_mode', JSON.stringify(assistantWideMode))
  }, [assistantWideMode])

  const toggleNav = () => setNavCollapsed((prev: boolean) => !prev)
  const toggleAssistant = () => setAssistantCollapsed((prev: boolean) => !prev)

  // The tour needs the nav expanded to anchor onto its items, regardless of
  // the user's saved preference.
  const navShown = !navCollapsed || tourActive

  // Calculate widths
  const navWidth = navShown ? 'w-56' : 'w-10'
  const assistantWidth = assistantCollapsed ? 'w-10' : (assistantWideMode ? 'w-[624px]' : 'w-[480px]')

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Top navigation bar */}
      <TopBar />

      {/* Main content area: Nav + Main + Assistant (all side-by-side, not overlays) */}
      <div className="flex flex-1 overflow-hidden gap-0">
        {/* Left sidebar navigation - collapsible with smooth slide effect */}
        <div className={`${navWidth} border-r border-gray-200 bg-white overflow-hidden flex flex-col transition-[width] duration-300 ease-in-out`}>
          {!navShown ? (
            // Collapsed nav bar with menu button
            <div className="w-full h-full flex flex-col items-center py-3 gap-2 bg-gray-50 border-r border-gray-200">
              <button
                onClick={toggleNav}
                title="Expand navigation"
                className="text-gray-600 hover:text-gray-900 hover:bg-gray-200 transition-colors p-1.5 rounded-md"
                aria-label="Expand navigation"
              >
                <Menu className="w-5 h-5" />
              </button>
            </div>
          ) : (
            // Full nav with collapse button
            <div className="w-full h-full flex flex-col">
              <div className="flex-shrink-0 px-3 py-2 border-b border-gray-200 bg-gray-50 flex items-center justify-end">
                <button
                  onClick={toggleNav}
                  title="Collapse navigation"
                  className="text-gray-600 hover:text-gray-900 hover:bg-gray-200 transition-colors p-1.5 rounded-md"
                  aria-label="Collapse navigation"
                >
                  <Menu className="w-5 h-5" />
                </button>
              </div>
              <SideNav />
            </div>
          )}
        </div>

        {/* Center: main content area - squishes when nav/assistant expand */}
        <main className="flex-1 overflow-auto transition-all duration-300 bg-gray-100">
          <NoAccessGate appName="payguard">
            <div className="min-h-full p-6 pt-16">
              <ErrorBoundary>
                {children}
              </ErrorBoundary>
            </div>
          </NoAccessGate>
        </main>

        {/* Right: persistent assistant drawer - real drawer, not overlay */}
        <div className={`${assistantWidth} border-l border-gray-200 bg-white overflow-hidden flex flex-col transition-[width] duration-300 ease-in-out`}>
          {/* Contained so any assistant runtime error degrades the drawer only,
              never the whole page. */}
          <ErrorBoundary>
            <AssistantDrawer
              isCollapsed={assistantCollapsed}
              onToggle={toggleAssistant}
              context={assistantContext}
              isWideMode={assistantWideMode}
              onToggleWideMode={() => setAssistantWideMode((prev: boolean) => !prev)}
            />
          </ErrorBoundary>
        </div>
      </div>

      {/* New-user spotlight walkthrough (auto-starts once; relaunch from TopBar ?) */}
      <SpotlightTour />
    </div>
  )
}
