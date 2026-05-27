import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { useCurrentUser } from '../hooks/useCurrentUser'
import PerformanceView, { Period, PeriodToggle, PerformanceData } from '../components/dashboard/PerformanceView'

const PERIOD_LABEL: Record<Period, string> = {
  week: 'Past 7 days', month: 'Past 30 days', quarter: 'Past 90 days',
}

const ALL_ANALYSTS = '__all__'

export default function TeamPerformancePage() {
  const { users } = useCurrentUser()
  const [period, setPeriod] = useState<Period>('month')
  const [analystId, setAnalystId] = useState<string>(ALL_ANALYSTS)

  const analysts = users
    .filter((u) => u.role === 'analyst' && u.is_active)
    .sort((a, b) => a.full_name.localeCompare(b.full_name))

  const url = analystId === ALL_ANALYSTS
    ? `/dashboard/team?period=${period}`
    : `/dashboard/team?period=${period}&analyst_id=${encodeURIComponent(analystId)}`

  const { data, isLoading } = useQuery<PerformanceData>({
    queryKey: ['team-dashboard', period, analystId],
    queryFn: async () => (await api.get<PerformanceData>(url)).data,
  })

  const selectedName = analystId === ALL_ANALYSTS
    ? 'All analysts'
    : analysts.find((u) => u.id === analystId)?.full_name ?? '?'

  return (
    <div className="max-w-6xl">
      <div className="flex items-end justify-between gap-3 mb-5 flex-wrap">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Team Performance</h2>
          <p className="text-sm text-gray-500 mt-1">
            {selectedName} · {PERIOD_LABEL[period]}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={analystId}
            onChange={(e) => setAnalystId(e.target.value)}
            className="px-3 py-2 text-sm bg-white border border-gray-200 rounded-lg
                       focus:outline-none focus:ring-2 focus:ring-[#FE017D]/30 focus:border-[#FE017D]"
          >
            <option value={ALL_ANALYSTS}>All analysts (team aggregate)</option>
            {analysts.map((u) => (
              <option key={u.id} value={u.id}>{u.full_name}</option>
            ))}
          </select>
          <PeriodToggle period={period} onChange={setPeriod} />
        </div>
      </div>
      <PerformanceView
        data={data}
        isLoading={isLoading}
        pipelineLabel={analystId === ALL_ANALYSTS ? 'Team active pipeline' : `${selectedName} — active pipeline`}
      />
    </div>
  )
}
