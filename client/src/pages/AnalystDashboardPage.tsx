import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { useCurrentUser } from '../hooks/useCurrentUser'
import PerformanceView, { Period, PeriodToggle, PerformanceData } from '../components/dashboard/PerformanceView'

const PERIOD_LABEL: Record<Period, string> = {
  week: 'Past 7 days', month: 'Past 30 days', quarter: 'Past 90 days',
}

export default function AnalystDashboardPage() {
  const { currentUser } = useCurrentUser()
  const [period, setPeriod] = useState<Period>('month')

  const { data, isLoading } = useQuery<PerformanceData>({
    queryKey: ['my-dashboard', period],
    queryFn: async () => (await api.get<PerformanceData>(`/dashboard/me?period=${period}`)).data,
  })

  return (
    <div className="max-w-6xl">
      <div className="flex items-end justify-between gap-3 mb-5">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Performance</h1>
          <p className="text-sm text-gray-500 mt-1">
            {currentUser?.full_name} · {PERIOD_LABEL[period]}
          </p>
        </div>
        <PeriodToggle period={period} onChange={setPeriod} />
      </div>
      <PerformanceView data={data} isLoading={isLoading} pipelineLabel="My active pipeline" />
    </div>
  )
}
