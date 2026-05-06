import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { getCases } from '../services/caseService'
import type { WorklistFilters, CaseListResponse } from '../types'

export function useCases(filters: WorklistFilters) {
  return useQuery<CaseListResponse, Error>({
    queryKey: ['cases', filters],
    queryFn: () => getCases(filters),
    placeholderData: keepPreviousData,
  })
}
