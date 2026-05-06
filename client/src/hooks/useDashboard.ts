import { useQuery } from '@tanstack/react-query'
import { getDashboard } from '../services/dashboardService'
import type { DashboardData } from '../types'

export function useDashboard() {
  return useQuery<DashboardData, Error>({
    queryKey: ['dashboard'],
    queryFn: getDashboard,
    refetchInterval: 60_000,
  })
}
