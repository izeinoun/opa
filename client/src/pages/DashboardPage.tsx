import { useState } from 'react'
import { TrendingUp, TrendingDown, AlertTriangle, BarChart2, DollarSign, Users } from 'lucide-react'
import { useDashboard } from '../hooks/useDashboard'
import { useCurrentUser } from '../hooks/useCurrentUser'
import AnalystDashboardPage from './AnalystDashboardPage'
import TeamPerformancePage from './TeamPerformancePage'
import AgingChart from '../components/charts/AgingChart'
import WorkloadChart from '../components/charts/WorkloadChart'
import RecoveryChart from '../components/charts/RecoveryChart'
import DetectorChart from '../components/charts/DetectorChart'
import StatusDonut from '../components/charts/StatusDonut'
import { formatCurrency, formatPercent } from '../utils/formatUtils'
import { card } from '../utils/designSystem'

const KPI_META = [
  { icon: BarChart2,     color: 'text-blue-500',   bg: 'bg-blue-50'   },
  { icon: AlertTriangle, color: 'text-amber-500',   bg: 'bg-amber-50'  },
  { icon: DollarSign,    color: 'text-teal-600',    bg: 'bg-teal-50'   },
  { icon: TrendingUp,    color: 'text-purple-500',  bg: 'bg-purple-50' },
]

function formatKPIValue(value: number | string, unit?: string): string {
  if (typeof value === 'string') return value
  if (unit === '$') return formatCurrency(value)
  if (unit === '%') return formatPercent(value)
  return value.toLocaleString()
}

export default function DashboardPage() {
  const { currentUser } = useCurrentUser()
  // Analysts get their own focused performance view.
  if (currentUser?.role === 'analyst') {
    return <AnalystDashboardPage />
  }

  // Supervisors / admins: toggle between Operations (existing) and Team Performance (new).
  return <SupervisorDashboard />
}

function SupervisorDashboard() {
  const [view, setView] = useState<'ops' | 'team'>('ops')

  return (
    <div className="space-y-5">
      <div className="inline-flex bg-gray-100 rounded-lg p-0.5 self-start">
        {([
          { v: 'ops',  label: 'Operations'        },
          { v: 'team', label: 'Team Performance'  },
        ] as const).map((opt) => (
          <button key={opt.v}
            onClick={() => setView(opt.v)}
            className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-colors ${
              view === opt.v ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
      {view === 'ops' ? <OpsDashboard /> : <TeamPerformancePage />}
    </div>
  )
}

function OpsDashboard() {
  const { data, isLoading, error } = useDashboard()

  if (isLoading) {
    return (
      <div className="space-y-5 animate-pulse">
        <div className="grid grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 bg-white rounded-xl border border-gray-200" />
          ))}
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="h-64 bg-white rounded-xl border border-gray-200" />
          <div className="h-64 bg-white rounded-xl border border-gray-200" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="h-64 bg-white rounded-xl border border-gray-200" />
          <div className="h-64 bg-white rounded-xl border border-gray-200" />
        </div>
        <div className="h-64 bg-white rounded-xl border border-gray-200" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-2" />
          <p className="text-gray-900 font-medium">Failed to load dashboard</p>
          <p className="text-sm text-gray-500 mt-1">Check the API connection and try again.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <span className="text-xs text-gray-400">Auto-refreshes every 60s</span>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {data.kpis.map((kpi, idx) => {
          const meta = KPI_META[idx] ?? { icon: Users, color: 'text-gray-400', bg: 'bg-gray-50' }
          const Icon = meta.icon
          return (
            <div key={idx} className={`${card} hover:shadow-md transition-all duration-200`}>
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-gray-500 font-medium">{kpi.label}</span>
                <span className={`w-8 h-8 rounded-lg ${meta.bg} flex items-center justify-center`}>
                  <Icon className={`w-4 h-4 ${meta.color}`} />
                </span>
              </div>
              <p className="text-3xl font-bold text-gray-900">
                {formatKPIValue(kpi.value, kpi.unit)}
              </p>
              {kpi.delta !== undefined && (
                <div className="flex items-center gap-1 mt-2">
                  {kpi.delta >= 0
                    ? <TrendingUp className="w-3 h-3 text-green-500" />
                    : <TrendingDown className="w-3 h-3 text-red-500" />}
                  <span className={`text-xs font-medium ${kpi.delta >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {kpi.delta >= 0 ? '+' : ''}{kpi.delta}% vs last month
                  </span>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Status Donut + Aging */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <StatusDonut data={data.status_distribution} />
        <AgingChart data={data.aging} />
      </div>

      {/* Workload + Detector */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <WorkloadChart data={data.workload} />
        <DetectorChart data={data.detectors} />
      </div>

      {/* Recovery Chart */}
      <RecoveryChart data={data.recovery} />
    </div>
  )
}
